"""
Provider Analyzer (Phase 20.3 - Adaptive Performance)
==================================================
Turns latency_tracker.py's raw event log into an opinion -
path_optimizer.py needs to know not just "what happened" but "which
candidate is the better bet right now", and that requires combining
reliability (success_rate) and speed (latency percentiles) into a
single comparable score, plus noticing when a provider that used to
be fine is trending worse before it fully breaks.

Deliberately simple/heuristic scoring, same spirit as
resource_optimizer.py and urgency_calculator.py: a fixed weighted
blend of success_rate and normalized latency, never a learned model.
score() is stateless given latency_tracker.py's current data - this
module holds no opinion of its own between calls except the
snapshot history it keeps for trend detection.

Trend detection: analyze_provider() records a snapshot of the
current window's avg_ms/success_rate to provider_snapshots each time
it's called, then compares the two most recent snapshots to call the
provider "improving"/"stable"/"degrading". Needs at least two
snapshots spaced apart to say anything - a single call always
reports "insufficient data" for trend, which is honest rather than
guessing from one data point.

Storage: database/performance_metrics.db, table provider_snapshots
(this module's own table, shared db file with the rest of
adaptive_performance/, same pattern as predictive_preparation.db in
Phase 20.2).
"""

import sqlite3
import threading
import time
from pathlib import Path
from typing import Dict, List, Optional

from core.logger import get_logger
from intelligence.adaptive_performance.latency_tracker import get_latency_tracker

logger = get_logger("ultron.provider_analyzer")

DB_PATH = Path(__file__).resolve().parent.parent.parent / "database" / "performance_metrics.db"

_instance: Optional["ProviderAnalyzer"] = None
_instance_lock = threading.Lock()

# how success_rate and latency blend into a single 0..1 score -
# reliability weighted higher than speed, a fast provider that fails
# often is worse than a slower one that doesn't
_WEIGHT_SUCCESS_RATE = 0.6
_WEIGHT_LATENCY = 0.4

# latency at/above this is treated as "as bad as it gets" for
# normalization purposes - not a hard cutoff, just where the score
# curve bottoms out
_LATENCY_FLOOR_MS = 50.0
_LATENCY_CEILING_MS = 8000.0

# two snapshots need to be at least this far apart for a trend
# comparison to mean anything - otherwise back-to-back calls within
# the same burst would look like a "trend" from pure noise
_MIN_SNAPSHOT_GAP_SECONDS = 30.0

# relative change in blended score between snapshots beyond which we
# call it a trend rather than noise
_TREND_THRESHOLD = 0.08


class ProviderAnalyzer:
    """analyze_provider() to score one candidate; rank_providers() to
    order several for the same operation."""

    def __init__(self, db_path: Path = DB_PATH):
        self._db_path = db_path
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
        self._conn.execute("""CREATE TABLE IF NOT EXISTS provider_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                provider TEXT,
                operation TEXT,
                score REAL,
                avg_ms REAL,
                success_rate REAL,
                sample_count INTEGER,
                timestamp REAL
            )""")
        self._conn.commit()
        self._tracker = get_latency_tracker()

    def analyze_provider(
        self, provider: str, operation: Optional[str] = None, window_seconds: Optional[float] = 3600.0
    ) -> Dict:
        stats = self._tracker.get_stats(provider=provider, operation=operation, window_seconds=window_seconds)
        reasons: List[str] = []

        if stats["count"] == 0:
            reasons.append(
                f"no recorded calls for '{provider}'" + (f"/{operation}" if operation else "") + " in this window"
            )
            return {
                "provider": provider,
                "operation": operation,
                "score": None,
                "success_rate": None,
                "avg_ms": None,
                "sample_count": 0,
                "trend": "insufficient data",
                "reasons": reasons,
            }

        score = self._score(stats["success_rate"], stats["avg_ms"])
        reasons.append(
            f"success_rate {stats['success_rate']:.2f}, avg latency {stats['avg_ms']:.0f}ms "
            f"over {stats['count']} call(s) -> score {score:.3f}"
        )

        trend, trend_reason = self._trend(provider, operation, score)
        reasons.append(trend_reason)

        self._save_snapshot(provider, operation, score, stats["avg_ms"], stats["success_rate"], stats["count"])

        return {
            "provider": provider,
            "operation": operation,
            "score": round(score, 3),
            "success_rate": stats["success_rate"],
            "avg_ms": stats["avg_ms"],
            "p95_ms": stats["p95_ms"],
            "sample_count": stats["count"],
            "trend": trend,
            "reasons": reasons,
        }

    def rank_providers(
        self, providers: List[str], operation: Optional[str] = None, window_seconds: Optional[float] = 3600.0
    ) -> List[Dict]:
        analyzed = [self.analyze_provider(p, operation=operation, window_seconds=window_seconds) for p in providers]
        # providers with no data yet sort last, not first - an
        # unknown quantity shouldn't outrank a proven-good one
        return sorted(analyzed, key=lambda a: (a["score"] is None, -(a["score"] or 0.0)))

    def get_recent_snapshots(self, provider: str, operation: Optional[str] = None, limit: int = 20) -> List[Dict]:
        with self._lock:
            rows = self._conn.execute(
                """SELECT provider, operation, score, avg_ms, success_rate, sample_count, timestamp
                   FROM provider_snapshots WHERE provider = ?
                   ORDER BY id DESC LIMIT ?""",
                (provider, limit),
            ).fetchall()
        snapshots = [
            {
                "provider": p,
                "operation": o,
                "score": s,
                "avg_ms": a,
                "success_rate": sr,
                "sample_count": sc,
                "timestamp": ts,
            }
            for p, o, s, a, sr, sc, ts in rows
        ]
        if operation is not None:
            snapshots = [s for s in snapshots if s["operation"] == operation]
        return snapshots

    def _trend(self, provider: str, operation: Optional[str], current_score: float) -> (str, str):
        with self._lock:
            rows = self._conn.execute(
                """SELECT score, timestamp FROM provider_snapshots
                   WHERE provider = ? AND operation IS ?
                   ORDER BY id DESC LIMIT 1""",
                (provider, operation),
            ).fetchall()
        if not rows:
            return "insufficient data", "no prior snapshot to compare against yet"

        prev_score, prev_ts = rows[0]
        gap = time.time() - prev_ts
        if gap < _MIN_SNAPSHOT_GAP_SECONDS:
            return "insufficient data", f"last snapshot only {gap:.0f}s ago - too soon to call a trend"

        if prev_score <= 0:
            return "stable", "prior score was zero/unset - treating as stable"

        delta = (current_score - prev_score) / prev_score
        if delta >= _TREND_THRESHOLD:
            return "improving", f"score up {delta:+.0%} vs previous snapshot"
        if delta <= -_TREND_THRESHOLD:
            return "degrading", f"score down {delta:+.0%} vs previous snapshot"
        return "stable", f"score change {delta:+.0%} vs previous snapshot - within noise"

    def _save_snapshot(
        self,
        provider: str,
        operation: Optional[str],
        score: float,
        avg_ms: float,
        success_rate: float,
        sample_count: int,
    ) -> None:
        with self._lock:
            self._conn.execute(
                """INSERT INTO provider_snapshots
                   (provider, operation, score, avg_ms, success_rate, sample_count, timestamp)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (provider, operation, score, avg_ms, success_rate, sample_count, time.time()),
            )
            self._conn.commit()

    @staticmethod
    def _score(success_rate: float, avg_ms: float) -> float:
        span = _LATENCY_CEILING_MS - _LATENCY_FLOOR_MS
        clamped = max(_LATENCY_FLOOR_MS, min(_LATENCY_CEILING_MS, avg_ms))
        latency_score = 1.0 - ((clamped - _LATENCY_FLOOR_MS) / span)
        return _WEIGHT_SUCCESS_RATE * success_rate + _WEIGHT_LATENCY * latency_score


def get_provider_analyzer() -> ProviderAnalyzer:
    """Process-wide ProviderAnalyzer singleton."""
    global _instance
    if _instance is None:
        with _instance_lock:
            if _instance is None:
                _instance = ProviderAnalyzer()
    return _instance
