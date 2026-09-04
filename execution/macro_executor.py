"""
Macro Executor (Phase 24 - Execution)
==================================================
Single entry point for the execution/ package - mirrors
performance_engine.py's role in Phase 20.3 and self_healing_engine.py's
role in Phase 19.5 (a thin orchestrator over otherwise-independent
sub-modules that still work fine called directly).

A "macro" here is a plain ordered list of step dicts, each naming one
of app_launcher.py/auto_player.py/web_automator.py's actions - a
single macro can mix an app launch, an RPA script replay, and a
browser action, which none of those three modules can do alone since
each only knows its own kind of step:

    {"type": "app_launch",  "app_name": "...", "args": [...], "as_admin": False, "wait": False}
    {"type": "rpa_script",  "name": "...", "speed": 1.0, "loop": 1}
    {"type": "macro",       "name": "...", "speed": 1.0}
    {"type": "web_scroll",  "direction": "down", "amount": 300, "browser": None}
    {"type": "web_navigate","action": "back", "browser": None}
    {"type": "web_script",  "name": "...", "stop_on_error": True}

execute() runs each step in order. On a failed step, if
heal_on_failure is set (default True) it hands the failure to
self_healer.py, which may retry it automatically via
self_healing_engine.py's strategy plan; the step only counts as
failed in the run summary if healing didn't recover it. stop_on_error
controls whether a still-failed step aborts the remaining steps or
the macro just keeps going.

Storage: database/execution.db, tables macro_runs (one row per
execute() call) and macro_steps (one row per step; this module's own
tables, shared with app_launcher.py's/auto_player.py's/
web_automator.py's/self_healer.py's own tables in the same file).

Purely additive - nothing in Phase 1-23 imports from here, and this
module does not modify app_launcher.py/auto_player.py/
web_automator.py/self_healer.py's own behavior when called directly;
it only sequences calls to them.
"""

import sqlite3
import threading
import time
import uuid
from pathlib import Path
from typing import Dict, List, Optional

from core.logger import get_logger
from execution.app_launcher import get_app_launcher
from execution.auto_player import get_auto_player
from execution.web_automator import get_web_automator
from execution.self_healer import get_self_healer

logger = get_logger("ultron.macro_executor")

DB_PATH = Path(__file__).resolve().parent.parent / "database" / "execution.db"

_instance: Optional["MacroExecutor"] = None
_instance_lock = threading.Lock()

_VALID_TYPES = {"app_launch", "rpa_script", "macro", "web_scroll", "web_navigate", "web_script"}


class MacroExecutor:
    """Orchestrates app_launcher / auto_player / web_automator /
    self_healer into one execute() call over a mixed step list."""

    def __init__(self, db_path: Path = DB_PATH):
        self._db_path = db_path
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
        self._conn.execute("""CREATE TABLE IF NOT EXISTS macro_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT,
                macro_name TEXT,
                step_count INTEGER,
                succeeded_count INTEGER,
                healed_count INTEGER,
                outcome TEXT,
                duration_ms REAL,
                timestamp REAL
            )""")
        self._conn.execute("""CREATE TABLE IF NOT EXISTS macro_steps (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT,
                step_index INTEGER,
                step_type TEXT,
                success INTEGER,
                healed INTEGER,
                error TEXT,
                timestamp REAL
            )""")
        self._conn.commit()

        self._apps = get_app_launcher()
        self._player = get_auto_player()
        self._web = get_web_automator()
        self._healer = get_self_healer()

    def execute(
        self,
        steps: List[Dict],
        macro_name: Optional[str] = None,
        heal_on_failure: bool = True,
        stop_on_error: bool = True,
        max_heal_attempts: int = 3,
    ) -> Dict:
        """Run a mixed sequence of steps in order. Returns a run summary
        plus the per-step results, in the order they were attempted."""
        run_id = str(uuid.uuid4())
        macro_name = macro_name or f"macro-{run_id[:8]}"
        t0 = time.time()

        step_results: List[Dict] = []
        succeeded = 0
        healed = 0
        aborted = False

        for index, step in enumerate(steps):
            step_type = step.get("type")
            if step_type not in _VALID_TYPES:
                outcome = {"success": False, "error": f"unknown step type '{step_type}'"}
            else:
                outcome = self._run_step(step_type, step)

            success = bool(outcome.get("success"))
            was_healed = False

            if not success and heal_on_failure and step_type in _VALID_TYPES:
                heal_result = self._heal_step(step_type, step, outcome.get("error"), max_heal_attempts)
                if heal_result and heal_result.get("outcome") in ("healed", "healed_via_fallback"):
                    was_healed = True
                    success = True
                    healed += 1

            step_results.append(
                {
                    "index": index,
                    "type": step_type,
                    "success": success,
                    "healed": was_healed,
                    "error": outcome.get("error"),
                }
            )
            self._log_step(run_id, index, step_type, success, was_healed, outcome.get("error"))

            if success:
                succeeded += 1
            elif stop_on_error:
                aborted = True
                break

        duration_ms = (time.time() - t0) * 1000
        outcome = "completed" if succeeded == len(steps) else ("aborted" if aborted else "partial")
        self._log_run(run_id, macro_name, len(steps), succeeded, healed, outcome, duration_ms)

        return {
            "run_id": run_id,
            "macro_name": macro_name,
            "outcome": outcome,
            "step_count": len(steps),
            "succeeded_count": succeeded,
            "healed_count": healed,
            "duration_ms": duration_ms,
            "steps": step_results,
        }

    def _run_step(self, step_type: str, step: Dict) -> Dict:
        try:
            if step_type == "app_launch":
                if step.get("wait"):
                    return self._apps.launch_and_wait(step["app_name"], timeout=step.get("timeout", 10.0))
                return self._apps.launch(step["app_name"], args=step.get("args"), as_admin=step.get("as_admin", False))

            if step_type == "rpa_script":
                return self._player.play_script(step["name"], speed=step.get("speed", 1.0), loop=step.get("loop", 1))

            if step_type == "macro":
                return self._player.play_macro(step["name"], speed=step.get("speed", 1.0))

            if step_type == "web_scroll":
                return self._web.live_scroll(
                    direction=step.get("direction", "down"), amount=step.get("amount", 300), browser=step.get("browser")
                )

            if step_type == "web_navigate":
                return self._web.live_navigate(step["action"], browser=step.get("browser"))

            if step_type == "web_script":
                return self._web.script_play(step["name"], stop_on_error=step.get("stop_on_error", True))

            return {"success": False, "error": f"unhandled step type '{step_type}'"}
        except KeyError as exc:
            return {"success": False, "error": f"step missing required field {exc}"}
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    def _heal_step(self, step_type: str, step: Dict, error: Optional[str], max_attempts: int) -> Optional[Dict]:
        try:
            if step_type == "app_launch":
                return self._healer.heal_app_launch(
                    step["app_name"], error=error, args=step.get("args"), max_attempts=max_attempts
                )
            if step_type in ("rpa_script", "macro"):
                kind = "macro" if step_type == "macro" else "script"
                return self._healer.heal_playback(
                    kind, step["name"], error=error, speed=step.get("speed", 1.0), max_attempts=max_attempts
                )
            if step_type in ("web_scroll", "web_navigate", "web_script"):
                mode = {"web_scroll": "live_scroll", "web_navigate": "live_navigate", "web_script": "script_play"}[
                    step_type
                ]
                target = step.get("action") or step.get("name") or ""
                return self._healer.heal_web(mode, target, error=error, max_attempts=max_attempts)
        except Exception as exc:
            logger.info(f"macro_executor: healing attempt for {step_type} raised: {exc}")
        return None

    def get_recent_runs(self, macro_name: Optional[str] = None, limit: int = 20) -> List[Dict]:
        with self._lock:
            if macro_name:
                rows = self._conn.execute(
                    """SELECT run_id, macro_name, step_count, succeeded_count, healed_count,
                              outcome, duration_ms, timestamp
                       FROM macro_runs WHERE macro_name = ? ORDER BY id DESC LIMIT ?""",
                    (macro_name, limit),
                ).fetchall()
            else:
                rows = self._conn.execute(
                    """SELECT run_id, macro_name, step_count, succeeded_count, healed_count,
                              outcome, duration_ms, timestamp
                       FROM macro_runs ORDER BY id DESC LIMIT ?""",
                    (limit,),
                ).fetchall()
        return [
            {
                "run_id": rid,
                "macro_name": mn,
                "step_count": sc,
                "succeeded_count": sk,
                "healed_count": hc,
                "outcome": o,
                "duration_ms": d,
                "timestamp": ts,
            }
            for rid, mn, sc, sk, hc, o, d, ts in rows
        ]

    def get_run_steps(self, run_id: str) -> List[Dict]:
        with self._lock:
            rows = self._conn.execute(
                """SELECT step_index, step_type, success, healed, error, timestamp
                   FROM macro_steps WHERE run_id = ? ORDER BY step_index ASC""",
                (run_id,),
            ).fetchall()
        return [
            {"index": i, "type": t, "success": bool(s), "healed": bool(h), "error": e, "timestamp": ts}
            for i, t, s, h, e, ts in rows
        ]

    def _log_run(
        self,
        run_id: str,
        macro_name: str,
        step_count: int,
        succeeded_count: int,
        healed_count: int,
        outcome: str,
        duration_ms: float,
    ) -> None:
        with self._lock:
            self._conn.execute(
                """INSERT INTO macro_runs
                   (run_id, macro_name, step_count, succeeded_count, healed_count, outcome,
                    duration_ms, timestamp)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (run_id, macro_name, step_count, succeeded_count, healed_count, outcome, duration_ms, time.time()),
            )
            self._conn.commit()
        logger.info(
            f"macro_executor: '{macro_name}' ({run_id[:8]}) -> {outcome} "
            f"({succeeded_count}/{step_count} ok, {healed_count} healed)"
        )

    def _log_step(
        self, run_id: str, index: int, step_type: str, success: bool, healed: bool, error: Optional[str]
    ) -> None:
        with self._lock:
            self._conn.execute(
                """INSERT INTO macro_steps (run_id, step_index, step_type, success, healed, error, timestamp)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (run_id, index, step_type, 1 if success else 0, 1 if healed else 0, error, time.time()),
            )
            self._conn.commit()


def get_macro_executor() -> MacroExecutor:
    """Process-wide MacroExecutor singleton."""
    global _instance
    if _instance is None:
        with _instance_lock:
            if _instance is None:
                _instance = MacroExecutor()
    return _instance
