"""
Rollback (Phase 30 - Verification)
======================================
Nothing in the codebase currently undoes an action once it's run -
intelligence/self_healing/ retries or falls back to an *alternative*
action, it never reverses the one that already happened. This module
is a real (if intentionally simple) undo engine: a per-run stack of
(action_name, undo_fn, undo_args) entries, pushed by
core/orchestrator.py right after execution/action_manager.py reports
success, popped and executed in reverse order when
failure_detector.py's escalation ladder reaches "rollback".

Only actions with a *registered* undo handler are reversible - most
read-only or already-idempotent tools (queries, launches of apps that
were already running) don't need one and are simply skipped on
unwind. Registering an undo handler is opt-in per action name, kept
here rather than scattered across windows/*.py tool modules so
orchestrator.py has one place to check "is this reversible" before
deciding whether a rollback is even possible for a given step.
"""

import threading
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

from core.logger import get_logger

logger = get_logger("ultron.verification.rollback")


@dataclass
class UndoEntry:
    action_name: str
    undo_fn: Callable[..., Any]
    undo_args: Dict[str, Any]
    label: str = ""


# Registered per action_name -> Callable(**undo_args) -> None.
# Populated by whichever module knows how to reverse a given action
# (e.g. execution/app_launcher.py could register "launch_app" ->
# a function that closes the process it just opened). Empty by
# default - only actions someone has explicitly wired in are ever
# rolled back.
_UNDO_REGISTRY: Dict[str, Callable] = {}


def register_undo(action_name: str, undo_fn: Callable) -> None:
    _UNDO_REGISTRY[action_name] = undo_fn


def is_reversible(action_name: str) -> bool:
    return action_name in _UNDO_REGISTRY


class RollbackEngine:
    def __init__(self):
        self._stack: List[UndoEntry] = []
        self._lock = threading.Lock()

    def push(self, action_name: str, undo_args: Optional[Dict[str, Any]] = None, label: str = "") -> bool:
        """Call right after a successful action, only if
        is_reversible(action_name). Returns False (and pushes nothing)
        if no undo handler is registered, so callers can call this
        unconditionally without checking is_reversible() themselves
        first."""
        undo_fn = _UNDO_REGISTRY.get(action_name)
        if undo_fn is None:
            return False
        with self._lock:
            self._stack.append(UndoEntry(action_name, undo_fn, undo_args or {}, label))
        return True

    def rollback_last(self) -> Dict:
        with self._lock:
            if not self._stack:
                return {"success": False, "error": "nothing to roll back"}
            entry = self._stack.pop()
        try:
            entry.undo_fn(**entry.undo_args)
            logger.info(f"Rolled back '{entry.action_name}' ({entry.label})")
            return {"success": True, "action": entry.action_name}
        except Exception as e:
            logger.error(f"Rollback failed for '{entry.action_name}': {e}")
            return {"success": False, "action": entry.action_name, "error": str(e)}

    def rollback_all(self) -> List[Dict]:
        results = []
        while True:
            with self._lock:
                if not self._stack:
                    break
            results.append(self.rollback_last())
        return results

    def clear(self):
        with self._lock:
            self._stack.clear()

    def depth(self) -> int:
        with self._lock:
            return len(self._stack)


def new_rollback_engine() -> RollbackEngine:
    """Factory, not a singleton - like stop_conditions.py, each
    orchestrated run should get its own undo stack so one goal's
    rollback never accidentally unwinds a different goal's actions."""
    return RollbackEngine()
