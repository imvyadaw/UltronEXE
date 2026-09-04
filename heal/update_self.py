"""
Update Self (HEAL)
=====================
Version bookkeeping, not a deployer - this module never pulls code,
runs pip/git, or replaces a running file. record_update() logs that a
new version was applied (by whatever external process actually did
the deploying) along with freeform notes, and current_version()/
needs_update() let a caller compare what's on file against a
caller-supplied "latest available" string. A rollback_point can be
marked so mark_rollback()/last_rollback_point() give a caller
something to fall back to if a newer version misbehaves - again, this
module only remembers which version that was; the actual rollback
mechanics belong to restart.py plus whatever the caller does with the
version string.
"""

import json
import os
import time
from typing import Dict, List, Optional

STATE_FILE_ENV = "SELF_MANAGEMENT_UPDATE_SELF_FILE"
DEFAULT_STATE_FILE = "data/self_management/update_self.json"


class UpdateSelf:
    """Version history and rollback-point bookkeeping. Use
    get_update_self(). Never deploys or rolls back anything itself."""

    def _state_path(self) -> str:
        path = os.environ.get(STATE_FILE_ENV, DEFAULT_STATE_FILE)
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        return path

    def _read_state(self) -> Dict:
        path = self._state_path()
        if not os.path.exists(path):
            return {"history": [], "rollback_point": None}
        with open(path) as fh:
            return json.load(fh)

    def _write_state(self, data: Dict) -> None:
        with open(self._state_path(), "w") as fh:
            json.dump(data, fh)

    def record_update(self, version: str, notes: str = "") -> Dict:
        """Logs that `version` is now the current version, with
        optional freeform `notes` (what changed, who/what applied
        it). This call only records the fact - it doesn't install
        anything. Returns {"success": bool, "error":
        Optional[str]}."""
        if not version:
            return {"success": False, "error": "version required"}
        data = self._read_state()
        data["history"].append({"version": version, "notes": notes, "timestamp": time.time()})
        self._write_state(data)
        return {"success": True, "error": None}

    def current_version(self) -> Optional[str]:
        """The most recently recorded version, or None if
        record_update() has never been called."""
        history = self._read_state()["history"]
        return history[-1]["version"] if history else None

    def needs_update(self, latest_available: str) -> Dict:
        """Compares `latest_available` (a version string supplied by
        the caller - this module has no way to check anywhere for
        what's actually latest) against current_version() by simple
        string inequality. Returns {"needs_update": bool,
        "current": Optional[str], "latest": str}. A None current
        version always counts as needing update."""
        current = self.current_version()
        return {"needs_update": current != latest_available, "current": current, "latest": latest_available}

    def history(self, limit: int = 20) -> List[Dict]:
        """Up to `limit` most recent recorded updates, oldest
        first."""
        return self._read_state()["history"][-limit:]

    def mark_rollback(self, version: Optional[str] = None) -> Dict:
        """Marks `version` (or current_version() if omitted) as the
        rollback point a caller should fall back to. Returns
        {"success": bool, "rollback_point": Optional[str], "error":
        Optional[str]}. Fails if no version is available to mark
        (nothing recorded yet and none supplied)."""
        target = version if version is not None else self.current_version()
        if target is None:
            return {"success": False, "rollback_point": None, "error": "no version to mark"}
        data = self._read_state()
        data["rollback_point"] = target
        self._write_state(data)
        return {"success": True, "rollback_point": target, "error": None}

    def last_rollback_point(self) -> Optional[str]:
        """The version string last marked via mark_rollback(), or
        None if none has been marked."""
        return self._read_state()["rollback_point"]


_update_self: Optional[UpdateSelf] = None


def get_update_self() -> UpdateSelf:
    global _update_self
    if _update_self is None:
        _update_self = UpdateSelf()
    return _update_self
