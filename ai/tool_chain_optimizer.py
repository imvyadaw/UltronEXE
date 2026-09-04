"""
Tool-Chain Optimizer (P1)
=========================
Distinct from ai/tool_selector.py (keyword match, "which one tool for
this message") - this module is "given several tools that could all
do the job, or a planned sequence of tools, which is actually worth
calling based on how they've performed for real" and "should this
multi-step chain be reordered/pruned".

Every tool call made through core/action_pipeline.py's ActionPipeline
is recorded here (success, latency, and which other tools were called
in the same chain) so ranking reflects this Ultron install's actual
history - a flaky network tool or one that's started timing out drops
in score without anyone hand-editing a preference list.

Storage: database/tool_chain_stats.db, tables tool_stats / chain_log.
Read-heavy, so ranking is a plain weighted score computed on read
rather than maintained incrementally - simpler and fast enough at the
call volumes a single-user assistant sees.
"""

import json
import sqlite3
import threading
import time
from pathlib import Path
from typing import Dict, List, Optional

DB_PATH = Path(__file__).resolve().parent.parent / "database" / "tool_chain_stats.db"

# Weight given to recency vs raw success rate when ranking - a tool that
# used to fail a lot but has succeeded its last several calls should
# recover its ranking faster than a naive all-time average would allow.
RECENCY_HALF_LIFE_SECONDS = 7 * 24 * 3600  # 1 week


class ToolChainOptimizer:
    def __init__(self, db_path: Path = DB_PATH):
        self._db_path = db_path
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
        self._conn.execute("""CREATE TABLE IF NOT EXISTS tool_stats (
                tool_name TEXT PRIMARY KEY,
                total_calls INTEGER DEFAULT 0,
                success_count INTEGER DEFAULT 0,
                fail_count INTEGER DEFAULT 0,
                total_latency_ms REAL DEFAULT 0,
                last_used_at REAL,
                last_success_at REAL,
                last_error TEXT
            )""")
        self._conn.execute("""CREATE TABLE IF NOT EXISTS chain_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_context TEXT,
                tools_json TEXT,
                outcome TEXT,
                timestamp REAL
            )""")
        self._conn.commit()

    # -- recording ------------------------------------------------------
    def record_execution(
        self, tool_name: str, success: bool, latency_ms: Optional[float] = None, error: Optional[str] = None
    ):
        """Call this after every real tool dispatch. Cheap and defensive -
        a caller (core/action_pipeline.py) should never let a stats
        recording failure break the actual action it's recording."""
        now = time.time()
        latency_ms = latency_ms or 0.0
        with self._lock:
            row = self._conn.execute(
                "SELECT total_calls, success_count, fail_count, total_latency_ms FROM tool_stats WHERE tool_name = ?",
                (tool_name,),
            ).fetchone()
            if row is None:
                self._conn.execute(
                    "INSERT INTO tool_stats (tool_name, total_calls, success_count, fail_count, "
                    "total_latency_ms, last_used_at, last_success_at, last_error) VALUES (?, 1, ?, ?, ?, ?, ?, ?)",
                    (
                        tool_name,
                        1 if success else 0,
                        0 if success else 1,
                        latency_ms,
                        now,
                        now if success else None,
                        None if success else error,
                    ),
                )
            else:
                total, succ, fail, total_lat = row
                self._conn.execute(
                    "UPDATE tool_stats SET total_calls = ?, success_count = ?, fail_count = ?, "
                    "total_latency_ms = ?, last_used_at = ?, last_success_at = COALESCE(?, last_success_at), "
                    "last_error = ? WHERE tool_name = ?",
                    (
                        total + 1,
                        succ + (1 if success else 0),
                        fail + (0 if success else 1),
                        total_lat + latency_ms,
                        now,
                        now if success else None,
                        None if success else error,
                        tool_name,
                    ),
                )
            self._conn.commit()

    def record_chain(self, tools: List[str], outcome: str, task_context: str = ""):
        """Log a completed multi-tool chain (outcome: 'success' | 'failed' |
        'partial') so future optimize_chain() calls for a similar
        task_context can prefer sequences that actually worked before."""
        with self._lock:
            self._conn.execute(
                "INSERT INTO chain_log (task_context, tools_json, outcome, timestamp) VALUES (?, ?, ?, ?)",
                (task_context, json.dumps(tools), outcome, time.time()),
            )
            self._conn.commit()

    # -- scoring ------------------------------------------------------
    def get_stats(self, tool_name: str) -> Dict:
        row = self._conn.execute(
            "SELECT total_calls, success_count, fail_count, total_latency_ms, last_used_at, "
            "last_success_at, last_error FROM tool_stats WHERE tool_name = ?",
            (tool_name,),
        ).fetchone()
        if row is None:
            return {
                "tool_name": tool_name,
                "total_calls": 0,
                "success_count": 0,
                "fail_count": 0,
                "success_rate": None,
                "avg_latency_ms": None,
                "score": 0.5,  # neutral prior for an unseen tool
                "last_used_at": None,
                "last_error": None,
            }
        total, succ, fail, total_lat, last_used, last_success, last_error = row
        success_rate = succ / total if total else None
        avg_latency = total_lat / total if total else None
        return {
            "tool_name": tool_name,
            "total_calls": total,
            "success_count": succ,
            "fail_count": fail,
            "success_rate": success_rate,
            "avg_latency_ms": avg_latency,
            "score": self._score(succ, fail, last_used),
            "last_used_at": last_used,
            "last_error": last_error,
        }

    def _score(self, succ: int, fail: int, last_used_at: Optional[float]) -> float:
        """0..1 composite: success rate with a recency-weighted decay so an
        old string of failures matters less than a recent one, plus a
        Bayesian prior (start at 0.5 with no data instead of 0) so a
        brand-new tool isn't unfairly ranked below a mediocre proven one
        after just its first call."""
        total = succ + fail
        if total == 0:
            return 0.5
        prior_weight = 2.0  # equivalent to 2 "average" pseudo-calls
        raw = (succ + prior_weight * 0.5) / (total + prior_weight)
        if last_used_at:
            age = max(0.0, time.time() - last_used_at)
            recency = 0.5 ** (age / RECENCY_HALF_LIFE_SECONDS)
            # blend: stale stats drift back toward the neutral prior rather
            # than being trusted at full strength forever
            raw = raw * recency + 0.5 * (1 - recency)
        return round(min(1.0, max(0.0, raw)), 4)

    def rank_tools(self, candidates: List[str]) -> List[Dict]:
        """Given several tools that could all serve the same purpose (e.g.
        two different search backends, three different email senders),
        return them ranked best-first by real-world reliability."""
        ranked = [self.get_stats(t) for t in candidates]
        ranked.sort(key=lambda s: s["score"], reverse=True)
        return ranked

    def get_best_tool(self, candidates: List[str]) -> Optional[str]:
        ranked = self.rank_tools(candidates)
        return ranked[0]["tool_name"] if ranked else None

    def optimize_chain(self, tools: List[str]) -> Dict:
        """Reorders a planned tool sequence so historically slower/flakier
        steps that don't have to run first are pushed later, and flags any
        tool whose current score is low enough to warrant a fallback
        before the chain runs. Does NOT reorder when order is semantically
        required - callers should only pass tools whose relative order is
        actually flexible (e.g. independent lookups run before a final
        write step, not steps of a strict recipe)."""
        stats = {t: self.get_stats(t) for t in tools}
        ordered = sorted(tools, key=lambda t: stats[t]["score"], reverse=True)
        warnings = [
            f"{t} has a low reliability score ({stats[t]['score']}) - consider a fallback"
            for t in tools
            if stats[t]["total_calls"] >= 3 and stats[t]["score"] < 0.4
        ]
        return {"original_order": tools, "suggested_order": ordered, "stats": stats, "warnings": warnings}

    def get_report(self, limit: int = 20) -> List[Dict]:
        rows = self._conn.execute(
            "SELECT tool_name FROM tool_stats ORDER BY total_calls DESC LIMIT ?", (limit,)
        ).fetchall()
        return [self.get_stats(r[0]) for r in rows]


_instance: Optional[ToolChainOptimizer] = None
_instance_lock = threading.Lock()


def get_tool_chain_optimizer() -> ToolChainOptimizer:
    global _instance
    if _instance is None:
        with _instance_lock:
            if _instance is None:
                _instance = ToolChainOptimizer()
    return _instance
