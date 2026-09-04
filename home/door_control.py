"""
Door Control (HOME)
=======================
Lock/unlock for one or more smart locks, gated behind
PHASE_18_8_SECURITY's intruder_alert.py the same way that phase
gates face_lock.py/voice_lock.py: unlock() always logs its outcome
there via record_success()/record_failed_attempt() when that package
is importable, so repeated bad unlock codes on a real front door
count toward the same alert threshold as repeated bad faces/voices.
This module does not itself decide who's allowed to unlock a door -
it only accepts a `code` per lock (set via DOOR_<LOCK_ID>_CODE) and
reports success/failure, exactly the shape intruder_alert.py already
expects from a "source".

No vendor lock API is wired in (August, Schlage, etc. all differ);
every call updates a simulated registry under
data/smart_devices/doors.json, which is enough for routine.py and
anything above it to reason about current lock state. Swap
_actually_unlock()/_actually_lock() for a real vendor client if one
gets added later - callers of this module don't need to change.
"""

import json
import os
import time
from typing import Dict, List, Optional

try:
    from security.intruder_alert import get_intruder_alert

    _INTRUDER_ALERT_AVAILABLE = True
except Exception:
    _INTRUDER_ALERT_AVAILABLE = False

STATE_FILE_ENV = "SMART_DEVICES_DOORS_FILE"
DEFAULT_STATE_FILE = "data/smart_devices/doors.json"
CODE_ENV_TEMPLATE = "DOOR_{lock_id}_CODE"


class DoorControl:
    """Smart lock unlock/lock, backed by SECURITY's intruder alert
    counter. Use get_door_control()."""

    def _state_path(self) -> str:
        path = os.environ.get(STATE_FILE_ENV, DEFAULT_STATE_FILE)
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        return path

    def _read_state(self) -> Dict:
        path = self._state_path()
        if not os.path.exists(path):
            return {"doors": {}}
        with open(path) as fh:
            return json.load(fh)

    def _write_state(self, data: Dict) -> None:
        with open(self._state_path(), "w") as fh:
            json.dump(data, fh)

    def _expected_code(self, lock_id: str) -> Optional[str]:
        return os.environ.get(CODE_ENV_TEMPLATE.format(lock_id=lock_id.upper()))

    def _record(self, lock_id: str, success: bool) -> Optional[Dict]:
        """Mirrors the outcome into intruder_alert.py under source
        "door:<lock_id>", if that package is importable. Returns its
        alert dict, or None if the package isn't available."""
        if not _INTRUDER_ALERT_AVAILABLE:
            return None
        alert = get_intruder_alert()
        source = f"door:{lock_id}"
        if success:
            alert.record_success(source)
            return None
        return alert.record_failed_attempt(source)

    def unlock(self, lock_id: str, code: str) -> Dict:
        """Unlocks `lock_id` if `code` matches DOOR_<LOCK_ID>_CODE.
        A lock with no configured code always fails closed rather
        than accepting anything. Every attempt is mirrored into
        intruder_alert.py under "door:<lock_id>" when that package is
        available. Returns {"success": bool, "alert": Optional[dict],
        "error": Optional[str]}."""
        expected = self._expected_code(lock_id)
        if expected is None:
            return {"success": False, "alert": None, "error": f"no code configured for '{lock_id}'"}
        if code != expected:
            alert = self._record(lock_id, success=False)
            return {"success": False, "alert": alert, "error": "incorrect code"}
        self._record(lock_id, success=True)
        data = self._read_state()
        data["doors"][lock_id] = {"locked": False, "last_change": time.time()}
        self._write_state(data)
        return {"success": True, "alert": None, "error": None}

    def lock(self, lock_id: str) -> Dict:
        """Locks `lock_id`. No code required - locking is never the
        risky direction. Returns {"success": bool, "error":
        Optional[str]}."""
        data = self._read_state()
        data["doors"][lock_id] = {"locked": True, "last_change": time.time()}
        self._write_state(data)
        return {"success": True, "error": None}

    def is_locked(self, lock_id: str) -> Optional[bool]:
        """Last known lock state, or None if this lock has never been
        addressed by this module."""
        entry = self._read_state()["doors"].get(lock_id)
        return entry["locked"] if entry else None

    def list_doors(self) -> List[str]:
        """IDs of every lock this module has ever addressed."""
        return list(self._read_state()["doors"].keys())

    def lock_all(self) -> Dict:
        """Locks every door this module knows about - the one bulk
        action routine.py's "leaving home" scene needs. Returns
        {"success": bool, "locked": List[str], "error":
        Optional[str]}."""
        locked = []
        for lock_id in self.list_doors():
            self.lock(lock_id)
            locked.append(lock_id)
        return {"success": True, "locked": locked, "error": None}


_door_control: Optional[DoorControl] = None


def get_door_control() -> DoorControl:
    global _door_control
    if _door_control is None:
        _door_control = DoorControl()
    return _door_control
