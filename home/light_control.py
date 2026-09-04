"""
Light Control (HOME)
========================
On/off, brightness and color for whatever smart bulbs this build
knows about. Talks to a Philips Hue bridge via `phue` when it's
importable and a bridge IP is configured; otherwise every call
still works against a local simulated registry (a plain JSON file
under data/smart_devices/lights.json) so routine.py and anything
above it never has to special-case "no bridge on this machine."

Bridge pairing (pressing the physical Hue button, first-run auth) is
deliberately NOT handled here - that's a one-time setup step left to
whoever configures the bridge, same as this project keeps its own
CONNECT/*.py credentials in .env rather than re-deriving them at
runtime. This module only expects HUE_BRIDGE_IP and, once paired,
HUE_BRIDGE_USERNAME to already be set.
"""

import json
import os
from typing import Dict, List, Optional

try:
    from phue import Bridge

    _PHUE_AVAILABLE = True
except Exception:
    _PHUE_AVAILABLE = False

BRIDGE_IP_ENV = "HUE_BRIDGE_IP"
BRIDGE_USERNAME_ENV = "HUE_BRIDGE_USERNAME"
STATE_FILE_ENV = "SMART_DEVICES_LIGHTS_FILE"
DEFAULT_STATE_FILE = "data/smart_devices/lights.json"


class LightControl:
    """Smart bulb on/off/brightness/color. Use get_light_control()."""

    def __init__(self):
        self._bridge = None  # lazily connected

    def _state_path(self) -> str:
        path = os.environ.get(STATE_FILE_ENV, DEFAULT_STATE_FILE)
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        return path

    def _read_state(self) -> Dict:
        path = self._state_path()
        if not os.path.exists(path):
            return {"lights": {}}
        with open(path) as fh:
            return json.load(fh)

    def _write_state(self, data: Dict) -> None:
        with open(self._state_path(), "w") as fh:
            json.dump(data, fh)

    def is_bridge_available(self) -> bool:
        """Whether a real Hue bridge can be reached - `phue` is
        importable AND a bridge IP is configured. False just means
        every call below falls back to the simulated registry, not
        that it will fail."""
        return _PHUE_AVAILABLE and bool(os.environ.get(BRIDGE_IP_ENV))

    def _connect(self):
        if self._bridge is not None:
            return self._bridge
        ip = os.environ.get(BRIDGE_IP_ENV)
        username = os.environ.get(BRIDGE_USERNAME_ENV)
        try:
            self._bridge = Bridge(ip, username=username) if username else Bridge(ip)
            return self._bridge
        except Exception:
            self._bridge = None
            return None

    def _simulated_set(self, light_id: str, **fields) -> Dict:
        data = self._read_state()
        entry = data["lights"].setdefault(light_id, {"on": False, "brightness": 100, "color": None})
        entry.update({k: v for k, v in fields.items() if v is not None})
        self._write_state(data)
        return {"success": True, "simulated": True, "state": entry, "error": None}

    def turn_on(self, light_id: str, brightness: Optional[int] = None) -> Dict:
        """Turns `light_id` on, optionally setting brightness (0-100
        in this API; converted to Hue's 0-254 range on a real
        bridge). Returns {"success": bool, "simulated": bool,
        "state": dict, "error": Optional[str]}."""
        if self.is_bridge_available():
            bridge = self._connect()
            if bridge is not None:
                try:
                    command = {"on": True}
                    if brightness is not None:
                        command["bri"] = max(0, min(254, round(brightness * 254 / 100)))
                    bridge.set_light(light_id, command)
                    return {
                        "success": True,
                        "simulated": False,
                        "state": {"on": True, "brightness": brightness},
                        "error": None,
                    }
                except Exception as exc:
                    return {"success": False, "simulated": False, "state": None, "error": str(exc)}
        return self._simulated_set(light_id, on=True, brightness=brightness)

    def turn_off(self, light_id: str) -> Dict:
        """Turns `light_id` off. Returns {"success": bool,
        "simulated": bool, "state": dict, "error": Optional[str]}."""
        if self.is_bridge_available():
            bridge = self._connect()
            if bridge is not None:
                try:
                    bridge.set_light(light_id, {"on": False})
                    return {"success": True, "simulated": False, "state": {"on": False}, "error": None}
                except Exception as exc:
                    return {"success": False, "simulated": False, "state": None, "error": str(exc)}
        return self._simulated_set(light_id, on=False)

    def set_brightness(self, light_id: str, brightness: int) -> Dict:
        """Sets brightness 0-100 without changing on/off state.
        Returns the same shape as turn_on()."""
        if self.is_bridge_available():
            bridge = self._connect()
            if bridge is not None:
                try:
                    bridge.set_light(light_id, {"bri": max(0, min(254, round(brightness * 254 / 100)))})
                    return {"success": True, "simulated": False, "state": {"brightness": brightness}, "error": None}
                except Exception as exc:
                    return {"success": False, "simulated": False, "state": None, "error": str(exc)}
        return self._simulated_set(light_id, brightness=brightness)

    def set_color(self, light_id: str, hex_color: str) -> Dict:
        """Sets a bulb's color from a "#rrggbb" hex string. Real-
        bridge color conversion (hex -> CIE xy) is left unimplemented
        here - a bare Hue command with just "on" is sent alongside
        the simulated color record, so a real bulb still responds
        while the intended color is at least tracked locally. Returns
        the same shape as turn_on()."""
        if self.is_bridge_available():
            bridge = self._connect()
            if bridge is not None:
                try:
                    bridge.set_light(light_id, {"on": True})
                except Exception as exc:
                    return {"success": False, "simulated": False, "state": None, "error": str(exc)}
        return self._simulated_set(light_id, on=True, color=hex_color)

    def get_state(self, light_id: str) -> Dict:
        """Last known state for `light_id` (from the simulated
        registry regardless of bridge availability, since that's the
        one place this module keeps color/brightness history).
        Returns {"on": bool, "brightness": int, "color":
        Optional[str]}, defaulting to off/unknown if never set."""
        return self._read_state()["lights"].get(light_id, {"on": False, "brightness": 100, "color": None})

    def list_lights(self) -> List[str]:
        """IDs of every light this module has ever addressed."""
        return list(self._read_state()["lights"].keys())


_light_control: Optional[LightControl] = None


def get_light_control() -> LightControl:
    global _light_control
    if _light_control is None:
        _light_control = LightControl()
    return _light_control
