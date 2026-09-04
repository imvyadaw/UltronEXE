"""
Auto Optimizer (Phase 20.3 - Adaptive Performance)
==================================================
The only module in adaptive_performance/ that changes anything on its
own initiative rather than in direct response to a caller's request -
run_pass() periodically re-evaluates every registered operation and
applies the small, reversible adjustments the other modules already
know how to make: re-running path_optimizer.py's choose_path() so a
degrading provider gets routed around even if nothing happens to call
that operation for a while, and calling cache_strategist.py's
tune_ttl() so TTLs drift toward what each operation's real hit rate
supports.

Deliberately conservative about what counts as "automatic": this
module never invents a new heuristic of its own or overrides a
threshold in path_optimizer.py/cache_strategist.py - it only calls
the decision functions those modules already expose, on a schedule,
so their existing hysteresis/sample-size guards are what actually
protects against overreacting. Same "gatekeeper, not actor" relationship
resource_optimizer.py has to app_preloader.py/model_preloader.py/
context_preloader.py in Phase 20.2, just inverted - here this module
is the one on the schedule, calling into modules that already know
how to say no.

run_pass() runs synchronously and returns what it did, for a caller
that wants to trigger a pass on its own schedule (e.g. from an
existing task scheduler elsewhere in ULTRON). start_background()/
stop() are an optional convenience for a caller that would rather
this module drive its own timer thread; neither is required, and
Phase 20.3 does not call start_background() itself anywhere, in
keeping with "purely additive".

Storage: database/performance_metrics.db, table optimization_actions
(this module's own table, shared db file with the rest of
adaptive_performance/, same pattern as predictive_preparation.db in
Phase 20.2).
"""

import json
import sqlite3
import threading
import time
from pathlib import Path
from typing import Dict, List, Optional

from core.logger import get_logger
from intelligence.adaptive_performance.path_optimizer import get_path_optimizer
from intelligence.adaptive_performance.cache_strategist import get_cache_strategist

logger = get_logger("ultron.auto_optimizer")

DB_PATH = Path(__file__).resolve().parent.parent.parent / "database" / "performance_metrics.db"

_instance: Optional["AutoOptimizer"] = None
_instance_lock = threading.Lock()

_DEFAULT_INTERVAL_SECONDS = 900.0


class AutoOptimizer:
    """register_operation() to tell it what to keep tuned;
    run_pass() to run one tuning cycle now; start_background()/stop()
    for an optional self-driven timer thread."""

    def __init__(self, db_path: Path = DB_PATH):
        self._db_path = db_path
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
        self._conn.execute("""CREATE TABLE IF NOT EXISTS optimization_actions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                operation TEXT,
                action TEXT,
                detail_json TEXT,
                timestamp REAL
            )""")
        self._conn.commit()

        self._paths = get_path_optimizer()
        self._cache = get_cache_strategist()
        self._operations: List[str] = []

        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def register_operation(self, operation: str) -> None:
        """Tell this module an operation exists and should be swept
        by run_pass(). Independent of path_optimizer.py's own
        register_operation_providers() - an operation with no
        registered providers just gets skipped for the path step and
        still gets its cache TTL tuned."""
        with self._lock:
            if operation not in self._operations:
                self._operations.append(operation)

    def run_pass(self) -> Dict:
        with self._lock:
            operations = list(self._operations)

        actions = []
        for operation in operations:
            path_result = self._paths.choose_path(operation)
            if path_result["provider"] is not None:
                action = {
                    "operation": operation,
                    "action": "path_reevaluated",
                    "detail": {"provider": path_result["provider"], "reasons": path_result["reasons"]},
                }
                actions.append(action)
                self._log_action(operation, "path_reevaluated", action["detail"])

            ttl_result = self._cache.tune_ttl(operation)
            if ttl_result["adjusted"]:
                action = {"operation": operation, "action": "ttl_tuned", "detail": ttl_result}
                actions.append(action)
                self._log_action(operation, "ttl_tuned", ttl_result)

        logger.info(
            f"auto_optimizer: pass complete, {len(actions)} action(s) across " f"{len(operations)} operation(s)"
        )
        return {"operations_swept": len(operations), "actions": actions, "timestamp": time.time()}

    def start_background(self, interval_seconds: float = _DEFAULT_INTERVAL_SECONDS) -> None:
        if self._thread is not None and self._thread.is_alive():
            logger.debug("auto_optimizer: background loop already running")
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._loop, args=(interval_seconds,), daemon=True)
        self._thread.start()
        logger.info(f"auto_optimizer: background loop started, interval {interval_seconds:.0f}s")

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=5.0)
            self._thread = None

    def get_recent_actions(self, operation: Optional[str] = None, limit: int = 20) -> List[Dict]:
        with self._lock:
            if operation:
                rows = self._conn.execute(
                    """SELECT operation, action, detail_json, timestamp FROM optimization_actions
                       WHERE operation = ? ORDER BY id DESC LIMIT ?""",
                    (operation, limit),
                ).fetchall()
            else:
                rows = self._conn.execute(
                    """SELECT operation, action, detail_json, timestamp FROM optimization_actions
                       ORDER BY id DESC LIMIT ?""",
                    (limit,),
                ).fetchall()
        events = []
        for op, action, detail_json, ts in rows:
            try:
                detail = json.loads(detail_json) if detail_json else {}
            except Exception:
                detail = {}
            events.append({"operation": op, "action": action, "detail": detail, "timestamp": ts})
        return events

    def _loop(self, interval_seconds: float) -> None:
        while not self._stop_event.is_set():
            try:
                self.run_pass()
            except Exception as e:
                logger.warning(f"auto_optimizer: run_pass failed in background loop: {e}")
            self._stop_event.wait(interval_seconds)

    def _log_action(self, operation: str, action: str, detail: Dict) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO optimization_actions (operation, action, detail_json, timestamp) VALUES (?, ?, ?, ?)",
                (operation, action, json.dumps(detail), time.time()),
            )
            self._conn.commit()


def get_auto_optimizer() -> AutoOptimizer:
    """Process-wide AutoOptimizer singleton."""
    global _instance
    if _instance is None:
        with _instance_lock:
            if _instance is None:
                _instance = AutoOptimizer()
    return _instance
