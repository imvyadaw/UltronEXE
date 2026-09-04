"""
Latency Tracker (Phase 20.3 - Adaptive Performance)
==================================================
Ground truth for everything else in adaptive_performance/ - every
other module in this package answers its question ("which provider
is healthiest", "which path should we take", "is this worth caching")
by querying data this module recorded, not by measuring anything
itself. Same "one module owns the raw signal, everyone else derives
from it" pattern as next_task_predictor.py owning task_events for
predictive_preparation/ (Phase 20.2).

record() is the only way this module learns - it must be called by
whatever elsewhere in ULTRON actually dispatches a call to a provider
(LLM API client, tool executor, search backend, etc) once that call
finishes, success or failure. Phase 20.3 does not wire that call in
anywhere itself, in keeping with "purely additive" -
performance_engine.py exposes the same call at its own entry point
for a caller that wants one integration point instead of importing
this module directly.

Percentiles are computed from raw stored rows at query time rather
than maintained incrementally - simplest correct thing for the data
volumes this is expected to see, same "deliberately simple" posture
as urgency_calculator.py. A window_seconds filter keeps a long-lived
install from having every get_stats() call scan its entire history.

Storage: database/performance_metrics.db, table latency_events (this
module's own table; provider_analyzer.py/path_optimizer.py/
cache_strategist.py/auto_optimizer.py each keep their own tables in
the same database file, same sharing pattern as
predictive_preparation.db in Phase 20.2).
"""

import sqlite3
import threading
import time
from pathlib import Path
from typing import Dict, List, Optional

from core.logger import get_logger

logger = get_logger("ultron.latency_tracker")

DB_PATH = Path(__file__).resolve().parent.parent.parent / "database" / "performance_metrics.db"

_instance: Optional["LatencyTracker"] = None
_instance_lock = threading.Lock()

# a get_stats()/get_recent_events() call with no window_seconds given
# defaults to this - recent enough to reflect current behavior,
# without the caller having to think about it
_DEFAULT_WINDOW_SECONDS = 3600.0


class LatencyTracker:
    """record() to log a call's outcome; get_stats() to ask how a
    provider/operation has been performing."""

    def __init__(self, db_path: Path = DB_PATH):
        self._db_path = db_path
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
        self._conn.execute("""CREATE TABLE IF NOT EXISTS latency_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                provider TEXT,
                operation TEXT,
                latency_ms REAL,
                success INTEGER,
                error TEXT,
                timestamp REAL
            )""")
        self._conn.execute("CREATE INDEX IF NOT EXISTS idx_latency_provider_op ON latency_events (provider, operation)")
        self._conn.commit()

    def record(
        self, provider: str, operation: str, latency_ms: float, success: bool = True, error: Optional[str] = None
    ) -> Dict:
        now = time.time()
        with self._lock:
            self._conn.execute(
                """INSERT INTO latency_events (provider, operation, latency_ms, success, error, timestamp)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (provider, operation, latency_ms, 1 if success else 0, error, now),
            )
            self._conn.commit()
        if not success:
            logger.info(
                f"latency_tracker: '{provider}'/{operation} failed after {latency_ms:.0f}ms "
                f"({error or 'no error detail'})"
            )
        return {
            "provider": provider,
            "operation": operation,
            "latency_ms": latency_ms,
            "success": success,
            "error": error,
            "timestamp": now,
        }

    def get_stats(
        self,
        provider: Optional[str] = None,
        operation: Optional[str] = None,
        window_seconds: Optional[float] = _DEFAULT_WINDOW_SECONDS,
    ) -> Dict:
        rows = self._query(provider, operation, window_seconds)
        if not rows:
            return {
                "provider": provider,
                "operation": operation,
                "count": 0,
                "success_rate": None,
                "avg_ms": None,
                "p50_ms": None,
                "p95_ms": None,
                "p99_ms": None,
                "min_ms": None,
                "max_ms": None,
            }

        latencies = sorted(lat for lat, _ in rows)
        successes = sum(1 for _, ok in rows if ok)
        n = len(latencies)
        return {
            "provider": provider,
            "operation": operation,
            "count": n,
            "success_rate": round(successes / n, 4),
            "avg_ms": round(sum(latencies) / n, 2),
            "p50_ms": round(self._percentile(latencies, 50), 2),
            "p95_ms": round(self._percentile(latencies, 95), 2),
            "p99_ms": round(self._percentile(latencies, 99), 2),
            "min_ms": round(latencies[0], 2),
            "max_ms": round(latencies[-1], 2),
        }

    def get_recent_events(
        self, provider: Optional[str] = None, operation: Optional[str] = None, limit: int = 20
    ) -> List[Dict]:
        clauses, params = [], []
        if provider is not None:
            clauses.append("provider = ?")
            params.append(provider)
        if operation is not None:
            clauses.append("operation = ?")
            params.append(operation)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        params.append(limit)
        with self._lock:
            rows = self._conn.execute(
                f"""SELECT provider, operation, latency_ms, success, error, timestamp
                    FROM latency_events {where} ORDER BY id DESC LIMIT ?""",
                params,
            ).fetchall()
        return [
            {"provider": p, "operation": o, "latency_ms": lat, "success": bool(ok), "error": err, "timestamp": ts}
            for p, o, lat, ok, err, ts in rows
        ]

    def get_providers(self, operation: Optional[str] = None) -> List[str]:
        with self._lock:
            if operation is not None:
                rows = self._conn.execute(
                    "SELECT DISTINCT provider FROM latency_events WHERE operation = ?",
                    (operation,),
                ).fetchall()
            else:
                rows = self._conn.execute("SELECT DISTINCT provider FROM latency_events").fetchall()
        return [r[0] for r in rows]

    def _query(self, provider: Optional[str], operation: Optional[str], window_seconds: Optional[float]) -> List[tuple]:
        clauses, params = [], []
        if provider is not None:
            clauses.append("provider = ?")
            params.append(provider)
        if operation is not None:
            clauses.append("operation = ?")
            params.append(operation)
        if window_seconds is not None:
            clauses.append("timestamp >= ?")
            params.append(time.time() - window_seconds)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        with self._lock:
            rows = self._conn.execute(
                f"SELECT latency_ms, success FROM latency_events {where}",
                params,
            ).fetchall()
        return [(lat, bool(ok)) for lat, ok in rows]

    @staticmethod
    def _percentile(sorted_values: List[float], pct: float) -> float:
        if not sorted_values:
            return 0.0
        if len(sorted_values) == 1:
            return sorted_values[0]
        k = (pct / 100.0) * (len(sorted_values) - 1)
        lo, hi = int(k), min(int(k) + 1, len(sorted_values) - 1)
        if lo == hi:
            return sorted_values[lo]
        frac = k - lo
        return sorted_values[lo] + (sorted_values[hi] - sorted_values[lo]) * frac


def get_latency_tracker() -> LatencyTracker:
    """Process-wide LatencyTracker singleton."""
    global _instance
    if _instance is None:
        with _instance_lock:
            if _instance is None:
                _instance = LatencyTracker()
    return _instance
