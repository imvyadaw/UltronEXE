"""
Car Link (DEVICES)
======================
Lock/unlock and location lookup for a linked car, deliberately
mirroring HOME/door_control.py's shape rather than inventing a new
one: unlock() only accepts a per-car code (CAR_<CAR_ID>_CODE) and
mirrors every attempt into PHASE_18_8_SECURITY's intruder_alert.py
under source "car:<car_id>" when that package is importable, so a
string of wrong codes against a car counts toward the same alert
threshold as a front door or a face/voice check.

No vendor telematics API is wired in (every manufacturer's differs
and most require OAuth this project has no business holding without
the owner's own developer account) - every call updates a simulated
registry under data/smart_devices/cars.json. locate() in particular
returns whatever coordinates were last recorded via record_location(),
which a real integration would populate from its own polling loop;
this module never guesses or fabricates a location.
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

STATE_FILE_ENV = "SMART_DEVICES_CAR_FILE"
DEFAULT_STATE_FILE = "data/smart_devices/cars.json"
CODE_ENV_TEMPLATE = "CAR_{car_id}_CODE"


class CarLink:
    """Car lock/unlock/location, backed by SECURITY's intruder alert
    counter. Use get_car_link()."""

    def _state_path(self) -> str:
        path = os.environ.get(STATE_FILE_ENV, DEFAULT_STATE_FILE)
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        return path

    def _read_state(self) -> Dict:
        path = self._state_path()
        if not os.path.exists(path):
            return {"cars": {}}
        with open(path) as fh:
            return json.load(fh)

    def _write_state(self, data: Dict) -> None:
        with open(self._state_path(), "w") as fh:
            json.dump(data, fh)

    def _expected_code(self, car_id: str) -> Optional[str]:
        return os.environ.get(CODE_ENV_TEMPLATE.format(car_id=car_id.upper()))

    def _record(self, car_id: str, success: bool) -> Optional[Dict]:
        if not _INTRUDER_ALERT_AVAILABLE:
            return None
        alert = get_intruder_alert()
        source = f"car:{car_id}"
        if success:
            alert.record_success(source)
            return None
        return alert.record_failed_attempt(source)

    def unlock(self, car_id: str, code: str) -> Dict:
        """Unlocks `car_id` if `code` matches CAR_<CAR_ID>_CODE. A car
        with no configured code always fails closed. Every attempt is
        mirrored into intruder_alert.py under "car:<car_id>" when
        that package is available. Returns {"success": bool, "alert":
        Optional[dict], "error": Optional[str]}."""
        expected = self._expected_code(car_id)
        if expected is None:
            return {"success": False, "alert": None, "error": f"no code configured for '{car_id}'"}
        if code != expected:
            alert = self._record(car_id, success=False)
            return {"success": False, "alert": alert, "error": "incorrect code"}
        self._record(car_id, success=True)
        data = self._read_state()
        entry = data["cars"].setdefault(car_id, {})
        entry.update({"locked": False, "last_change": time.time()})
        data["cars"][car_id] = entry
        self._write_state(data)
        return {"success": True, "alert": None, "error": None}

    def lock(self, car_id: str) -> Dict:
        """Locks `car_id`. No code required. Returns {"success":
        bool, "error": Optional[str]}."""
        data = self._read_state()
        entry = data["cars"].setdefault(car_id, {})
        entry.update({"locked": True, "last_change": time.time()})
        data["cars"][car_id] = entry
        self._write_state(data)
        return {"success": True, "error": None}

    def is_locked(self, car_id: str) -> Optional[bool]:
        """Last known lock state, or None if never addressed."""
        entry = self._read_state()["cars"].get(car_id)
        return entry["locked"] if entry and "locked" in entry else None

    def record_location(self, car_id: str, latitude: float, longitude: float) -> Dict:
        """Records the car's current coordinates, as pushed by
        whatever real telematics integration a future build adds.
        This module never polls or fabricates a location itself.
        Returns {"success": bool, "error": Optional[str]}."""
        data = self._read_state()
        entry = data["cars"].setdefault(car_id, {})
        entry.update({"latitude": latitude, "longitude": longitude, "location_timestamp": time.time()})
        data["cars"][car_id] = entry
        self._write_state(data)
        return {"success": True, "error": None}

    def locate(self, car_id: str) -> Optional[Dict]:
        """Last recorded {"latitude": float, "longitude": float,
        "location_timestamp": float} for `car_id`, or None if no
        location has ever been recorded for it."""
        entry = self._read_state()["cars"].get(car_id, {})
        if "latitude" not in entry:
            return None
        return {
            "latitude": entry["latitude"],
            "longitude": entry["longitude"],
            "location_timestamp": entry["location_timestamp"],
        }

    def list_cars(self) -> List[str]:
        """IDs of every car this module has ever addressed."""
        return list(self._read_state()["cars"].keys())


_car_link: Optional[CarLink] = None


def get_car_link() -> CarLink:
    global _car_link
    if _car_link is None:
        _car_link = CarLink()
    return _car_link
