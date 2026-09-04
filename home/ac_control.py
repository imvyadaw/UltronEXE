"""
AC / Thermostat Control (HOME)
================================
Power, mode and target temperature for one or more climate units.
There's no single dominant Python library for smart thermostats the
way `phue` covers Hue, so this talks to whatever unit is configured
over plain HTTP (`requests`, optional) - the common ground most local
climate bridges and DIY ESP32/Tasmota setups expose - and otherwise
falls back to a simulated registry under data/smart_devices/climate.json,
same pattern as light_control.py.

A unit is "configured" once AC_<UNIT_ID>_HOST is set in the
environment (e.g. AC_LIVING_ROOM_HOST=192.168.1.42); anything without
a matching env var is simulated-only regardless of `requests`
availability. This module assumes each unit exposes simple
GET endpoints (/power, /mode, /target) - swap _send() for a
vendor-specific client if a real one is added later.
"""

import json
import os
from typing import Dict, List, Optional

try:
    import requests

    _REQUESTS_AVAILABLE = True
except Exception:
    _REQUESTS_AVAILABLE = False

STATE_FILE_ENV = "SMART_DEVICES_CLIMATE_FILE"
DEFAULT_STATE_FILE = "data/smart_devices/climate.json"
VALID_MODES = ("cool", "heat", "fan", "auto", "off")
REQUEST_TIMEOUT_SECONDS = 3


class ACControl:
    """Climate unit power/mode/temperature. Use get_ac_control()."""

    def _state_path(self) -> str:
        path = os.environ.get(STATE_FILE_ENV, DEFAULT_STATE_FILE)
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        return path

    def _read_state(self) -> Dict:
        path = self._state_path()
        if not os.path.exists(path):
            return {"units": {}}
        with open(path) as fh:
            return json.load(fh)

    def _write_state(self, data: Dict) -> None:
        with open(self._state_path(), "w") as fh:
            json.dump(data, fh)

    def _host_for(self, unit_id: str) -> Optional[str]:
        return os.environ.get(f"AC_{unit_id.upper()}_HOST")

    def is_unit_configured(self, unit_id: str) -> bool:
        """Whether `unit_id` has a real host configured - False means
        calls for it are simulated-only, not that they'll fail."""
        return _REQUESTS_AVAILABLE and bool(self._host_for(unit_id))

    def _send(self, unit_id: str, path: str, params: Dict) -> Optional[Dict]:
        host = self._host_for(unit_id)
        if not host or not _REQUESTS_AVAILABLE:
            return None
        try:
            response = requests.get(f"http://{host}{path}", params=params, timeout=REQUEST_TIMEOUT_SECONDS)
            response.raise_for_status()
            return {"ok": True}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def _simulated_set(self, unit_id: str, **fields) -> Dict:
        data = self._read_state()
        entry = data["units"].setdefault(unit_id, {"on": False, "mode": "off", "target_temp": 22})
        entry.update({k: v for k, v in fields.items() if v is not None})
        self._write_state(data)
        return {"success": True, "simulated": True, "state": entry, "error": None}

    def turn_on(self, unit_id: str, mode: str = "auto") -> Dict:
        """Turns `unit_id` on in `mode` (one of VALID_MODES). Returns
        {"success": bool, "simulated": bool, "state": dict, "error":
        Optional[str]}."""
        if mode not in VALID_MODES:
            return {"success": False, "simulated": False, "state": None, "error": f"mode must be one of {VALID_MODES}"}
        result = self._send(unit_id, "/power", {"state": "on", "mode": mode})
        if result is not None:
            if not result["ok"]:
                return {"success": False, "simulated": False, "state": None, "error": result["error"]}
            return {"success": True, "simulated": False, "state": {"on": True, "mode": mode}, "error": None}
        return self._simulated_set(unit_id, on=True, mode=mode)

    def turn_off(self, unit_id: str) -> Dict:
        """Turns `unit_id` off. Returns the same shape as turn_on()."""
        result = self._send(unit_id, "/power", {"state": "off"})
        if result is not None:
            if not result["ok"]:
                return {"success": False, "simulated": False, "state": None, "error": result["error"]}
            return {"success": True, "simulated": False, "state": {"on": False, "mode": "off"}, "error": None}
        return self._simulated_set(unit_id, on=False, mode="off")

    def set_target_temp(self, unit_id: str, celsius: float) -> Dict:
        """Sets the target temperature in Celsius without changing
        power/mode. Returns the same shape as turn_on()."""
        result = self._send(unit_id, "/target", {"celsius": celsius})
        if result is not None:
            if not result["ok"]:
                return {"success": False, "simulated": False, "state": None, "error": result["error"]}
            return {"success": True, "simulated": False, "state": {"target_temp": celsius}, "error": None}
        return self._simulated_set(unit_id, target_temp=celsius)

    def get_state(self, unit_id: str) -> Dict:
        """Last known state for `unit_id` from the simulated
        registry - the one place this module tracks mode/target
        history regardless of whether the unit is real. Returns
        {"on": bool, "mode": str, "target_temp": float}."""
        return self._read_state()["units"].get(unit_id, {"on": False, "mode": "off", "target_temp": 22})

    def list_units(self) -> List[str]:
        """IDs of every unit this module has ever addressed."""
        return list(self._read_state()["units"].keys())


_ac_control: Optional[ACControl] = None


def get_ac_control() -> ACControl:
    global _ac_control
    if _ac_control is None:
        _ac_control = ACControl()
    return _ac_control
