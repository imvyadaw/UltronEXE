"""
Self Healing Engine (Phase 19.5 - Self Healing)
===================================================
Single entry point for the self_healing/ package: given a failed
action (an exception, an error string, and/or a Phase 19.4
verification_engine result), run the full loop -
diagnose -> generate candidate strategies -> gate/track retries ->
fall back to alternate actions -> remember what worked - and log the
outcome.

Execution model: heal() takes an optional `executor` callable,
executor(strategy_name: str) -> bool (or it can raise, which counts
as failure). With an executor, this module actually drives recovery.
Without one, heal() runs in advisory/dry-run mode: it returns the
same ordered plan (diagnosis + strategies + fallback) without acting,
so a caller can inspect or execute it manually - the same
advisory-by-default shape as Phase 19.3's recovery_manager.

Storage: database/self_healing.db, table healing_runs (this
module's own table; failure_diagnoser.py is stateless, and
healing_memory.py / retry_manager.py / fallback_chain.py each keep
their own tables in the same database file).
"""

import json
import sqlite3
import threading
import time
from pathlib import Path
from typing import Callable, Dict, List, Optional

from core.logger import get_logger
from intelligence.self_healing.failure_diagnoser import get_failure_diagnoser
from intelligence.self_healing.strategy_generator import get_strategy_generator
from intelligence.self_healing.retry_manager import get_retry_manager
from intelligence.self_healing.fallback_chain import get_fallback_chain
from intelligence.self_healing.healing_memory import get_healing_memory

logger = get_logger("ultron.self_healing_engine")

DB_PATH = Path(__file__).resolve().parent.parent.parent / "database" / "self_healing.db"

_instance: Optional["SelfHealingEngine"] = None
_instance_lock = threading.Lock()


class SelfHealingEngine:
    """Orchestrates failure_diagnoser / strategy_generator /
    retry_manager / fallback_chain / healing_memory into one heal()
    call, and persists every healing run."""

    def __init__(self, db_path: Path = DB_PATH):
        self._db_path = db_path
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
        self._conn.execute("""CREATE TABLE IF NOT EXISTS healing_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                action_name TEXT,
                signature TEXT,
                outcome TEXT,
                strategies_tried_json TEXT,
                timestamp REAL
            )""")
        self._conn.commit()

        self._diagnoser = get_failure_diagnoser()
        self._strategies = get_strategy_generator()
        self._retry = get_retry_manager()
        self._fallback = get_fallback_chain()
        self._memory = get_healing_memory()

    def heal(
        self,
        action_name: str,
        error: Optional[str] = None,
        verification_result: Optional[Dict] = None,
        executor: Optional[Callable[[str], bool]] = None,
        max_attempts: int = 3,
    ) -> Dict:
        """Diagnose the failure and either execute recovery (executor
        given) or return the plan for a caller to execute (executor
        omitted). Returns:
            {
              "diagnosis": {...},
              "strategies": [...],           # the ordered plan
              "outcome": "healed"|"exhausted"|"planned",
              "strategy_tried": ... or None, # only set when executor ran
              "run_id": ...,
            }
        """
        diagnosis = self._diagnoser.diagnose(action_name, error=error, verification_result=verification_result)
        signature = diagnosis["signature"]
        strategies = self._strategies.generate(diagnosis)

        if executor is None:
            run_id = self._log_run(action_name, signature, "planned", [])
            return {
                "diagnosis": diagnosis,
                "strategies": strategies,
                "outcome": "planned",
                "strategy_tried": None,
                "run_id": run_id,
            }

        # retry_manager gates repeated heal() calls for this exact failure
        # (with backoff between them) - not the individual strategies tried
        # inside a single call, which are meant to all be tried right away.
        if not self._retry.should_retry(signature, max_attempts=max_attempts):
            run_id = self._log_run(action_name, signature, "exhausted", [])
            logger.info(f"'{action_name}' healing exhausted - retry budget used up for this failure")
            return {
                "diagnosis": diagnosis,
                "strategies": strategies,
                "outcome": "exhausted",
                "strategy_tried": None,
                "run_id": run_id,
            }
        self._retry.record_attempt(signature)

        tried: List[str] = []
        for strategy in strategies:
            name = strategy["name"]
            tried.append(name)
            try:
                success = bool(executor(name))
            except Exception as exc:
                logger.warning(f"strategy '{name}' for '{action_name}' raised: {exc}")
                success = False

            self._memory.record_outcome(
                signature, name, success, category=diagnosis["category"], action_name=action_name
            )
            if success:
                self._retry.reset(signature)
                run_id = self._log_run(action_name, signature, "healed", tried)
                logger.info(f"'{action_name}' healed via strategy '{name}'")
                return {
                    "diagnosis": diagnosis,
                    "strategies": strategies,
                    "outcome": "healed",
                    "strategy_tried": name,
                    "run_id": run_id,
                }

        # own strategies exhausted - try the registered fallback chain, if any
        fallback_action = self._fallback.get_next_fallback(action_name, attempted=tried)
        if fallback_action and executor is not None:
            try:
                success = bool(executor(fallback_action))
            except Exception as exc:
                logger.warning(f"fallback '{fallback_action}' for '{action_name}' raised: {exc}")
                success = False
            tried.append(fallback_action)
            if success:
                run_id = self._log_run(action_name, signature, "healed_via_fallback", tried)
                logger.info(f"'{action_name}' healed via fallback action '{fallback_action}'")
                return {
                    "diagnosis": diagnosis,
                    "strategies": strategies,
                    "outcome": "healed_via_fallback",
                    "strategy_tried": fallback_action,
                    "run_id": run_id,
                }

        run_id = self._log_run(action_name, signature, "exhausted", tried)
        logger.info(f"'{action_name}' healing exhausted after {tried}")
        return {
            "diagnosis": diagnosis,
            "strategies": strategies,
            "outcome": "exhausted",
            "strategy_tried": None,
            "run_id": run_id,
        }

    def _log_run(self, action_name: str, signature: str, outcome: str, strategies_tried: List[str]) -> int:
        now = time.time()
        with self._lock:
            cur = self._conn.execute(
                """INSERT INTO healing_runs (action_name, signature, outcome, strategies_tried_json, timestamp)
                   VALUES (?, ?, ?, ?, ?)""",
                (action_name, signature, outcome, json.dumps(strategies_tried), now),
            )
            self._conn.commit()
            return cur.lastrowid

    def get_history(self, action_name: Optional[str] = None, limit: int = 20) -> List[Dict]:
        with self._lock:
            if action_name:
                cur = self._conn.execute(
                    """SELECT id, action_name, signature, outcome, strategies_tried_json, timestamp
                       FROM healing_runs WHERE action_name = ? ORDER BY id DESC LIMIT ?""",
                    (action_name, limit),
                )
            else:
                cur = self._conn.execute(
                    """SELECT id, action_name, signature, outcome, strategies_tried_json, timestamp
                       FROM healing_runs ORDER BY id DESC LIMIT ?""",
                    (limit,),
                )
            rows = cur.fetchall()
        results = []
        for r in rows:
            try:
                tried = json.loads(r[4]) if r[4] else []
            except Exception:
                tried = []
            results.append(
                {
                    "id": r[0],
                    "action_name": r[1],
                    "signature": r[2],
                    "outcome": r[3],
                    "strategies_tried": tried,
                    "timestamp": r[5],
                }
            )
        return results


def get_self_healing_engine() -> SelfHealingEngine:
    """Process-wide SelfHealingEngine singleton."""
    global _instance
    if _instance is None:
        with _instance_lock:
            if _instance is None:
                _instance = SelfHealingEngine()
    return _instance
