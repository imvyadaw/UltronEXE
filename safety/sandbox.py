"""
Sandbox (Phase 4.1 - Learning & Safety)
=========================================
Where a newly-AUTO_EXECUTE-eligible action actually gets run the first
few times, instead of trusting the confidence number on faith. Not a
real OS-level sandbox (Ultron runs as the user's own process, same as
every other tool - see skill_creator/sandbox_tester.py and
ultron_shield/sandbox_executor.py for the process-isolation flavour of
"sandbox" elsewhere in this codebase); this is a *supervised-trial*
sandbox: run the real tool, but with a timeout, exception capture, and
mandatory result reporting back into learning/learner.py, for a fixed
number of runs before an action is allowed through
safety/action_approval.py with zero supervision.

Deliberately still refuses to ever touch core.permissions
PermissionGate.DESTRUCTIVE_TOOLS, even in a "trial" - trial or not,
those always come back needs_confirmation the same as
safety/trust_policy.py already guarantees; this is a second, independent
check on the same rule rather than trusting callers to have checked it
already.

Storage: database/sandbox_trials.db - one row per action, tracking how
many supervised trial runs it has left before action_approval.py stops
routing it through here.
"""

import sqlite3
import threading
import time
import traceback
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from core.logger import get_logger

logger = get_logger("ultron.safety.sandbox")

DB_PATH = Path(__file__).resolve().parent.parent / "database" / "sandbox_trials.db"

# how many AUTO_EXECUTE-eligible runs of a given action get routed
# through the supervised sandbox before it's allowed to run completely
# unattended via action_approval.py
SANDBOX_TRIAL_RUNS = 3
# a sandboxed run that hangs this long is treated as a failure - a
# runaway tool shouldn't be able to block an autonomous cycle forever
DEFAULT_TIMEOUT_SECONDS = 30


class SandboxExecutor:
    def __init__(self, db_path: Path = DB_PATH):
        self._db_path = db_path
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
        self._conn.execute("""CREATE TABLE IF NOT EXISTS trial_counts (
                action_name TEXT PRIMARY KEY,
                trials_used INTEGER NOT NULL DEFAULT 0,
                last_run_at REAL
            )""")
        self._conn.commit()

    def needs_trial(self, action_name: str) -> bool:
        with self._lock:
            row = self._conn.execute(
                "SELECT trials_used FROM trial_counts WHERE action_name = ?", (action_name,)
            ).fetchone()
        used = row[0] if row else 0
        return used < SANDBOX_TRIAL_RUNS

    def trials_remaining(self, action_name: str) -> int:
        with self._lock:
            row = self._conn.execute(
                "SELECT trials_used FROM trial_counts WHERE action_name = ?", (action_name,)
            ).fetchone()
        used = row[0] if row else 0
        return max(0, SANDBOX_TRIAL_RUNS - used)

    def _record_trial(self, action_name: str) -> None:
        with self._lock:
            self._conn.execute(
                """INSERT INTO trial_counts (action_name, trials_used, last_run_at)
                   VALUES (?, 1, ?)
                   ON CONFLICT(action_name) DO UPDATE SET
                       trials_used = trials_used + 1, last_run_at = excluded.last_run_at""",
                (action_name, time.time()),
            )
            self._conn.commit()

    def reset_trials(self, action_name: str) -> None:
        """Used after a policy/behaviour change makes past trials stale
        (e.g. the underlying tool implementation changed) - forces the
        action back through supervised runs before it's auto-executed
        unattended again."""
        with self._lock:
            self._conn.execute("DELETE FROM trial_counts WHERE action_name = ?", (action_name,))
            self._conn.commit()

    def run(
        self, action_name: str, executor: Callable[[], Any], timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS
    ) -> Dict:
        """Run `executor` (a zero-arg callable that performs the real
        tool call) under supervision. Always reports the outcome back
        into learning/learner.py and always returns a
        {"ok"/"error", "data"} envelope - matches the rest of the
        codebase's tool-return convention (see ai/tool_runtime.py) so
        callers can treat a sandboxed run like any other tool result.
        """
        from core.permissions import PermissionGate

        if PermissionGate().requires_confirmation(action_name):
            return {
                "ok": False,
                "error": f"'{action_name}' is a destructive tool - "
                "sandbox will not run it unsupervised, it must "
                "go through the normal confirmation flow",
            }

        result_holder: Dict[str, Any] = {}
        error_holder: Dict[str, str] = {}

        def _target():
            try:
                result_holder["data"] = executor()
            except Exception:
                error_holder["trace"] = traceback.format_exc()

        thread = threading.Thread(target=_target, daemon=True)
        start = time.time()
        thread.start()
        thread.join(timeout=timeout_seconds)
        elapsed = time.time() - start

        self._record_trial(action_name)

        from learning.learner import get_learner

        learner = get_learner()

        if thread.is_alive():
            logger.warning(f"sandbox: '{action_name}' timed out after {timeout_seconds}s")
            learner.observe(action_name, success=False, error=f"timeout after {timeout_seconds}s", source="sandbox")
            return {"ok": False, "error": "timeout", "elapsed": elapsed}

        if "trace" in error_holder:
            logger.warning(f"sandbox: '{action_name}' raised: {error_holder['trace'].splitlines()[-1]}")
            learner.observe(action_name, success=False, error=error_holder["trace"], source="sandbox")
            return {"ok": False, "error": error_holder["trace"], "elapsed": elapsed}

        learner.observe(action_name, success=True, source="sandbox")
        return {
            "ok": True,
            "data": result_holder.get("data"),
            "elapsed": elapsed,
            "trials_remaining": self.trials_remaining(action_name),
        }


_sandbox: Optional[SandboxExecutor] = None
_sandbox_lock = threading.Lock()


def get_sandbox_executor() -> SandboxExecutor:
    global _sandbox
    with _sandbox_lock:
        if _sandbox is None:
            _sandbox = SandboxExecutor()
        return _sandbox
