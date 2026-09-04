"""
Failure Pattern Learning Engine (P2)
====================================
Two things already track failures separately:
  - learning_engine/mistake_learner.py - per-action mistake counts with
    a simple "seen 2+ times -> caution" flag
  - self_healing/crash_analyzer.py - scans log files after the fact and
    groups Python tracebacks by signature

Neither watches failures *live* as they happen through
core/action_pipeline.py, and neither looks at *sequence* - whether a
tool tends to fail specifically after another particular tool ran
(e.g. a browser-automation tool that reliably fails if it's called
right after a window-close action, because the window it expects is
already gone). This module adds both: live ingestion via
record_outcome() (called from action_pipeline's stage 5, same place
ai/tool_chain_optimizer.py's stats are recorded) and precursor
correlation on top of per-tool error-signature clustering.

Deliberately additive, never blocking on its own - check_risk()
returns a risk label and reasons; core/action_pipeline.py /
intelligence/confidence_engine's decision_gate.py are the ones that
decide whether a "high" risk should actually stop or slow anything
down. This module only ever flags.

Storage: database/failure_patterns.db, tables failure_patterns /
chain_precursor_stats.
"""

import re
import sqlite3
import threading
import time
from collections import deque
from pathlib import Path
from typing import Deque, Dict, List, Optional, Tuple

DB_PATH = Path(__file__).resolve().parent.parent / "database" / "failure_patterns.db"

# How many-recent-calls of live history to keep in memory for precursor
# correlation. Session-local by design - "what usually runs right before
# this fails" is meant to reflect recent/current usage patterns, not the
# tool's entire lifetime history (which the sqlite tables already cover
# for the per-tool signature clustering below).
_PRECURSOR_WINDOW = 20

RECENCY_HALF_LIFE_SECONDS = 7 * 24 * 3600  # matches ai/tool_chain_optimizer.py

# Normalizes an error message into a bucketable signature: strip anything
# that looks like a path, a number, or a quoted literal, so
# "File not found: '/tmp/abc123.txt'" and "File not found: '/tmp/xyz.txt'"
# collapse into the same pattern instead of two separate ones.
_PATH_RE = re.compile(r"[\w./\\-]+\.\w{1,5}\b")
_NUM_RE = re.compile(r"\b\d+\b")
_QUOTED_RE = re.compile(r"'[^']*'|\"[^\"]*\"")


def _normalize_error(error: str) -> str:
    if not error:
        return "unknown_error"
    text = _QUOTED_RE.sub("<value>", error)
    text = _PATH_RE.sub("<path>", text)
    text = _NUM_RE.sub("<n>", text)
    return text.strip()[:160]


class FailurePatternEngine:
    def __init__(self, db_path: Path = DB_PATH):
        self._db_path = db_path
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
        self._conn.execute("""CREATE TABLE IF NOT EXISTS failure_patterns (
                tool_name TEXT,
                error_signature TEXT,
                occurrences INTEGER DEFAULT 0,
                first_seen REAL,
                last_seen REAL,
                sample_message TEXT,
                PRIMARY KEY (tool_name, error_signature)
            )""")
        self._conn.execute("""CREATE TABLE IF NOT EXISTS chain_precursor_stats (
                preceding_tool TEXT,
                failing_tool TEXT,
                co_occurrences INTEGER DEFAULT 0,
                failures_after INTEGER DEFAULT 0,
                PRIMARY KEY (preceding_tool, failing_tool)
            )""")
        self._conn.commit()
        # in-memory rolling history of (tool_name, success) for precursor
        # correlation; not persisted, resets per process (see class docstring)
        self._recent: Deque[Tuple[str, bool]] = deque(maxlen=_PRECURSOR_WINDOW)

    # -- ingestion ----------------------------------------------------
    def record_outcome(self, tool_name: str, success: bool, error: Optional[str] = None):
        """Call this from wherever a real tool execution completes - see
        core/action_pipeline.py stage 5. Cheap and defensive: never raises."""
        try:
            preceding = self._recent[-1][0] if self._recent else None
            with self._lock:
                if preceding:
                    self._conn.execute(
                        "INSERT INTO chain_precursor_stats (preceding_tool, failing_tool, co_occurrences, failures_after) "
                        "VALUES (?, ?, 1, ?) ON CONFLICT(preceding_tool, failing_tool) DO UPDATE SET "
                        "co_occurrences = co_occurrences + 1, failures_after = failures_after + ?",
                        (preceding, tool_name, 0 if success else 1, 0 if success else 1),
                    )
                if not success:
                    sig = _normalize_error(error or "")
                    now = time.time()
                    self._conn.execute(
                        "INSERT INTO failure_patterns (tool_name, error_signature, occurrences, first_seen, "
                        "last_seen, sample_message) VALUES (?, ?, 1, ?, ?, ?) "
                        "ON CONFLICT(tool_name, error_signature) DO UPDATE SET "
                        "occurrences = occurrences + 1, last_seen = ?",
                        (tool_name, sig, now, now, (error or "")[:300], now),
                    )
                self._conn.commit()
            self._recent.append((tool_name, success))
        except Exception:
            # Never let pattern-learning bookkeeping break the caller
            # (action_pipeline) that's reporting a real action's outcome.
            from core.error_trace import log_swallowed as _lsw

            _lsw("learning_engine.failure_pattern_engine.record_outcome")

    # -- querying ------------------------------------------------------
    def get_patterns(self, tool_name: Optional[str] = None, limit: int = 20) -> List[Dict]:
        if tool_name:
            rows = self._conn.execute(
                "SELECT tool_name, error_signature, occurrences, first_seen, last_seen, sample_message "
                "FROM failure_patterns WHERE tool_name = ? ORDER BY occurrences DESC LIMIT ?",
                (tool_name, limit),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT tool_name, error_signature, occurrences, first_seen, last_seen, sample_message "
                "FROM failure_patterns ORDER BY occurrences DESC LIMIT ?",
                (limit,),
            ).fetchall()
        patterns = []
        for tool, sig, occ, first, last, sample in rows:
            patterns.append(
                {
                    "tool_name": tool,
                    "error_signature": sig,
                    "occurrences": occ,
                    "first_seen": first,
                    "last_seen": last,
                    "sample_message": sample,
                    "risk_score": self._risk_score(occ, last),
                }
            )
        patterns.sort(key=lambda p: p["risk_score"], reverse=True)
        return patterns

    def _risk_score(self, occurrences: int, last_seen: float) -> float:
        age = max(0.0, time.time() - last_seen)
        recency = 0.5 ** (age / RECENCY_HALF_LIFE_SECONDS)
        frequency = min(1.0, occurrences / 5.0)  # 5+ occurrences = maxed-out frequency signal
        return round(frequency * recency, 4)

    def get_precursor_warning(self, tool_name: str) -> Optional[Dict]:
        """If some other tool has, historically, reliably preceded failures
        of `tool_name`, return that as a warning. Requires at least 3
        co-occurrences and a >=50% failure-after rate to avoid flagging
        noise from one or two coincidental failures."""
        rows = self._conn.execute(
            "SELECT preceding_tool, co_occurrences, failures_after FROM chain_precursor_stats "
            "WHERE failing_tool = ? AND co_occurrences >= 3 ORDER BY (1.0 * failures_after / co_occurrences) DESC LIMIT 1",
            (tool_name,),
        ).fetchone()
        if not rows:
            return None
        preceding, co, fails = rows
        rate = fails / co if co else 0.0
        if rate < 0.5:
            return None
        return {
            "preceding_tool": preceding,
            "failing_tool": tool_name,
            "co_occurrences": co,
            "failure_rate_after": round(rate, 2),
        }

    def check_risk(self, tool_name: str) -> Dict:
        """Empirical risk check before running a tool - complements
        intelligence.confidence_engine's decision_gate (which reasons
        about a single pending action's signals) with 'has this specific
        tool actually been failing in a recognizable way lately'."""
        patterns = self.get_patterns(tool_name, limit=5)
        precursor = self.get_precursor_warning(tool_name)
        top_score = patterns[0]["risk_score"] if patterns else 0.0
        if precursor:
            top_score = max(top_score, precursor["failure_rate_after"])
        risk = "high" if top_score >= 0.6 else "medium" if top_score >= 0.3 else "low"
        return {
            "tool_name": tool_name,
            "risk": risk,
            "risk_score": round(top_score, 4),
            "matched_patterns": patterns,
            "precursor_warning": precursor,
        }

    def get_report(self, limit: int = 15) -> Dict:
        return {
            "top_patterns": self.get_patterns(limit=limit),
            "precursor_pairs": self._top_precursor_pairs(limit=limit),
        }

    def _top_precursor_pairs(self, limit: int = 15) -> List[Dict]:
        rows = self._conn.execute(
            "SELECT preceding_tool, failing_tool, co_occurrences, failures_after FROM chain_precursor_stats "
            "WHERE co_occurrences >= 3 ORDER BY (1.0 * failures_after / co_occurrences) DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [
            {"preceding_tool": p, "failing_tool": f, "co_occurrences": co, "failure_rate_after": round(fa / co, 2)}
            for p, f, co, fa in rows
            if co
        ]


_instance: Optional[FailurePatternEngine] = None
_instance_lock = threading.Lock()


def get_failure_pattern_engine() -> FailurePatternEngine:
    global _instance
    if _instance is None:
        with _instance_lock:
            if _instance is None:
                _instance = FailurePatternEngine()
    return _instance
