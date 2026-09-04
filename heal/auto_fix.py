"""
Auto Fix (HEAL)
==================
A registry of known (component -> candidate fixes) mappings plus a
log of what's been tried, optionally reading health_check.py's
failing_components() to know what needs a fix. This module never
executes a fix itself - no shell commands, no restarts, no code
execution - register_fix() just files away a human-readable
description under a fix_id, and record_attempt() logs that some
external caller tried it and whether it worked. Keeping execution out
of this module entirely means a fix "registered" here can never
silently run something unreviewed; the actual applying is always a
deliberate action by whatever surface calls restart.py, a shell
script, or a person.

The health_check.py hook is import-guarded, so this module works
standalone (a caller can pass component names directly to
suggest_fix()) if 18.9.2's own HEAL/health_check.py isn't importable
for some reason - it's an internal-package convenience, not a hard
dependency.
"""

import json
import os
import time
from typing import Dict, List, Optional

try:
    from heal.health_check import get_health_check

    _HEALTH_CHECK_AVAILABLE = True
except Exception:
    _HEALTH_CHECK_AVAILABLE = False

STATE_FILE_ENV = "SELF_MANAGEMENT_AUTO_FIX_FILE"
DEFAULT_STATE_FILE = "data/self_management/auto_fix.json"


class AutoFix:
    """Known-fix registry and attempt log. Use get_auto_fix(). Never
    executes anything itself."""

    def _state_path(self) -> str:
        path = os.environ.get(STATE_FILE_ENV, DEFAULT_STATE_FILE)
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        return path

    def _read_state(self) -> Dict:
        path = self._state_path()
        if not os.path.exists(path):
            return {"fixes": {}, "attempts": []}
        with open(path) as fh:
            return json.load(fh)

    def _write_state(self, data: Dict) -> None:
        with open(self._state_path(), "w") as fh:
            json.dump(data, fh)

    def register_fix(self, component: str, fix_id: str, description: str) -> Dict:
        """Files `description` (plain text - what a human or caller
        should do, e.g. "clear the cache dir and re-run
        update_self.record_update()") under `fix_id` as a candidate
        fix for `component`. Re-registering the same fix_id for the
        same component overwrites its description. Returns
        {"success": bool, "error": Optional[str]}."""
        if not component or not fix_id:
            return {"success": False, "error": "component and fix_id required"}
        data = self._read_state()
        bucket = data["fixes"].setdefault(component, {})
        bucket[fix_id] = description
        self._write_state(data)
        return {"success": True, "error": None}

    def suggest_fix(self, component: str) -> List[Dict]:
        """Every registered fix for `component`, as a list of
        {"fix_id": str, "description": str}. Returns an empty list if
        nothing's registered for it - never invents a fix."""
        fixes = self._read_state()["fixes"].get(component, {})
        return [{"fix_id": fid, "description": desc} for fid, desc in fixes.items()]

    def suggest_for_failing(self) -> Dict:
        """Convenience wrapper: pulls health_check.py's
        failing_components() (if that module is importable) and
        returns {"component": [suggest_fix(component) result], ...}
        for each one, plus {"error": Optional[str]}. Returns
        {"error": "health_check not available"} if the import guard
        tripped, since there's no failing-component list to work
        from without it."""
        if not _HEALTH_CHECK_AVAILABLE:
            return {"error": "health_check not available"}
        failing = get_health_check().failing_components()
        return {"error": None, **{c: self.suggest_fix(c) for c in failing}}

    def record_attempt(self, component: str, fix_id: str, success: bool, notes: str = "") -> Dict:
        """Logs that `fix_id` was tried against `component` by
        whatever external caller actually applied it, and whether it
        worked. Purely a log entry - this call itself changes
        nothing about the component's state. Returns {"success":
        bool, "error": Optional[str]}."""
        if not component or not fix_id:
            return {"success": False, "error": "component and fix_id required"}
        data = self._read_state()
        data["attempts"].append(
            {
                "component": component,
                "fix_id": fix_id,
                "success": success,
                "notes": notes,
                "timestamp": time.time(),
            }
        )
        self._write_state(data)
        return {"success": True, "error": None}

    def attempt_history(self, component: Optional[str] = None, limit: int = 20) -> List[Dict]:
        """Up to `limit` most recent fix attempts, oldest first,
        optionally filtered to a single `component`."""
        attempts = self._read_state()["attempts"]
        if component is not None:
            attempts = [a for a in attempts if a["component"] == component]
        return attempts[-limit:]


_auto_fix: Optional[AutoFix] = None


def get_auto_fix() -> AutoFix:
    global _auto_fix
    if _auto_fix is None:
        _auto_fix = AutoFix()
    return _auto_fix
