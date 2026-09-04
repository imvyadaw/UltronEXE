"""
Path Optimizer (Phase 20.3 - Adaptive Performance)
==================================================
Where provider_analyzer.py's opinion becomes a decision. Given an
operation (e.g. "chat_completion", "web_search") and the candidate
providers registered for it, choose_path() returns which one to use
right now plus a fallback order - so a caller elsewhere in ULTRON
(the LLM router, a tool dispatcher) has one place to ask "who should
handle this" instead of re-deriving it from raw stats itself.

Whitelist-only, same posture as app_preloader.py's registry: nothing
is chosen for an operation that wasn't registered via
register_operation_providers(). Phase 20.3 ships this module with an
empty registry and does not guess at candidates itself, in keeping
with "purely additive" - a caller elsewhere in ULTRON is expected to
populate it once at startup.

Hysteresis: the top-ranked provider from provider_analyzer.py only
replaces the currently-sticky choice if it beats it by more than
_SWITCH_MARGIN, and not before _MIN_STICKY_SECONDS have passed -
otherwise two near-tied providers would flap back and forth on every
call as their scores jitter within noise, which is worse for actual
end-to-end latency than just staying put. Same "don't overreact to
every plausible signal" spirit as predictive_engine.py's
MAX_PREDICTIONS_TO_ACT_ON cap.

A provider whose success_rate falls below _MIN_SUCCESS_RATE is
skipped entirely regardless of how fast it is - a fast failure is
still a failure, and path_optimizer.py's whole job is to route
around that, not just around slowness.

Storage: database/performance_metrics.db, table path_decisions (this
module's own table, shared db file with the rest of
adaptive_performance/, same pattern as predictive_preparation.db in
Phase 20.2).
"""

import sqlite3
import threading
import time
from pathlib import Path
from typing import Dict, List, Optional

from core.logger import get_logger
from intelligence.adaptive_performance.provider_analyzer import get_provider_analyzer

logger = get_logger("ultron.path_optimizer")

DB_PATH = Path(__file__).resolve().parent.parent.parent / "database" / "performance_metrics.db"

_instance: Optional["PathOptimizer"] = None
_instance_lock = threading.Lock()

# a candidate below this success_rate is never chosen, no matter how
# fast it is or how much better everything else scores
_MIN_SUCCESS_RATE = 0.5

# how much better a challenger's score needs to be, relative to the
# current sticky choice, before we bother switching
_SWITCH_MARGIN = 0.10

# minimum time to stay on a choice before a challenger is even
# considered - keeps a single noisy call from triggering a switch
_MIN_STICKY_SECONDS = 60.0


class PathOptimizer:
    """register_operation_providers() to configure; choose_path() to
    ask which provider should handle an operation right now."""

    def __init__(self, db_path: Path = DB_PATH):
        self._db_path = db_path
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
        self._conn.execute("""CREATE TABLE IF NOT EXISTS path_decisions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                operation TEXT,
                chosen_provider TEXT,
                candidates_json TEXT,
                switched INTEGER,
                reason TEXT,
                timestamp REAL
            )""")
        self._conn.commit()

        self._analyzer = get_provider_analyzer()
        self._registry: Dict[str, List[str]] = {}
        # in-memory sticky state per operation - resets harmlessly on
        # restart, same spirit as next_task_predictor.py's _last_task
        self._sticky: Dict[str, Dict] = {}

    def register_operation_providers(self, operation: str, providers: List[str]) -> None:
        with self._lock:
            self._registry[operation] = list(providers)
        logger.info(f"path_optimizer: registered {len(providers)} candidate(s) for '{operation}'")

    def choose_path(self, operation: str, context: Optional[Dict] = None) -> Dict:
        with self._lock:
            candidates = list(self._registry.get(operation, []))

        if not candidates:
            return {
                "provider": None,
                "fallback_order": [],
                "reasons": [f"no providers registered for operation '{operation}'"],
            }

        ranked = self._analyzer.rank_providers(candidates, operation=operation)
        eligible = [r for r in ranked if r["score"] is not None and r["success_rate"] >= _MIN_SUCCESS_RATE]
        reasons: List[str] = []

        if not eligible:
            # nothing has both data and an acceptable success rate -
            # fall back to registration order rather than refusing to
            # answer at all, same "degrade gracefully" posture as
            # resource_optimizer.py without psutil
            reasons.append(
                "no candidate has an acceptable success_rate and sufficient data - "
                "falling back to registration order"
            )
            fallback_order = candidates
            chosen = fallback_order[0]
            switched = False
        else:
            best = eligible[0]
            fallback_order = [r["provider"] for r in eligible] + [
                c for c in candidates if c not in [r["provider"] for r in eligible]
            ]

            with self._lock:
                sticky = self._sticky.get(operation)

            if sticky is None:
                chosen = best["provider"]
                switched = True
                reasons.append(f"no sticky choice yet - starting on top-ranked '{chosen}' " f"(score {best['score']})")
            elif sticky["provider"] == best["provider"]:
                chosen = sticky["provider"]
                switched = False
                reasons.append(f"top-ranked candidate is already the sticky choice '{chosen}'")
            elif (time.time() - sticky["since"]) < _MIN_STICKY_SECONDS:
                chosen = sticky["provider"]
                switched = False
                reasons.append(f"staying on '{chosen}' - sticky window not yet elapsed")
            else:
                sticky_entry = next((r for r in ranked if r["provider"] == sticky["provider"]), None)
                sticky_score = sticky_entry["score"] if sticky_entry and sticky_entry["score"] is not None else 0.0
                if best["score"] - sticky_score > _SWITCH_MARGIN:
                    chosen = best["provider"]
                    switched = True
                    reasons.append(
                        f"switching '{sticky['provider']}' -> '{chosen}': score "
                        f"{best['score']} beats sticky {sticky_score} by more than margin"
                    )
                else:
                    chosen = sticky["provider"]
                    switched = False
                    reasons.append(
                        f"staying on '{chosen}' - challenger '{best['provider']}' " f"doesn't clear the switch margin"
                    )

            with self._lock:
                if switched or operation not in self._sticky:
                    self._sticky[operation] = {"provider": chosen, "since": time.time()}

        self._log_decision(operation, chosen, candidates, switched, "; ".join(reasons))
        return {"provider": chosen, "fallback_order": fallback_order, "reasons": reasons}

    def get_recent_decisions(self, operation: Optional[str] = None, limit: int = 20) -> List[Dict]:
        import json

        with self._lock:
            if operation:
                rows = self._conn.execute(
                    """SELECT operation, chosen_provider, candidates_json, switched, reason, timestamp
                       FROM path_decisions WHERE operation = ? ORDER BY id DESC LIMIT ?""",
                    (operation, limit),
                ).fetchall()
            else:
                rows = self._conn.execute(
                    """SELECT operation, chosen_provider, candidates_json, switched, reason, timestamp
                       FROM path_decisions ORDER BY id DESC LIMIT ?""",
                    (limit,),
                ).fetchall()
        events = []
        for op, provider, cand_json, switched, reason, ts in rows:
            try:
                candidates = json.loads(cand_json) if cand_json else []
            except Exception:
                candidates = []
            events.append(
                {
                    "operation": op,
                    "provider": provider,
                    "candidates": candidates,
                    "switched": bool(switched),
                    "reason": reason,
                    "timestamp": ts,
                }
            )
        return events

    def _log_decision(self, operation: str, chosen: str, candidates: List[str], switched: bool, reason: str) -> None:
        import json

        with self._lock:
            self._conn.execute(
                """INSERT INTO path_decisions (operation, chosen_provider, candidates_json, switched, reason, timestamp)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (operation, chosen, json.dumps(candidates), 1 if switched else 0, reason, time.time()),
            )
            self._conn.commit()


def get_path_optimizer() -> PathOptimizer:
    """Process-wide PathOptimizer singleton."""
    global _instance
    if _instance is None:
        with _instance_lock:
            if _instance is None:
                _instance = PathOptimizer()
    return _instance
