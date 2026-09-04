"""
TV Control (DEVICES)
========================
Power/volume/input/app-launch for a smart TV over Roku's External
Control Protocol - a plain unauthenticated HTTP POST to
http://<tv-ip>:8060/keypress/<KEY> - chosen over inventing a generic
protocol because ECP is real, well-documented, and needs no token or
pairing step beyond knowing the TV's IP, which keeps this module
consistent with the rest of DEVICES/ in never needing a secret to
degrade gracefully. Needs `requests`; without it, or without
TV_<TV_ID>_HOST configured, every call falls back to the same
simulated registry pattern as light_control.py/ac_control.py.

Only a handful of ECP keypresses are exposed (power, volume,
directional, select, home) rather than the full remote surface -
enough for routine.py's MOVIE_NIGHT scene and basic control, not a
complete Roku client. launch_app() uses ECP's separate /launch/<id>
endpoint and needs a numeric Roku channel id, which this module does
not look up on the caller's behalf.
"""

import json
import os
from typing import Dict, List, Optional

try:
    import requests

    _REQUESTS_AVAILABLE = True
except Exception:
    _REQUESTS_AVAILABLE = False

STATE_FILE_ENV = "SMART_DEVICES_TV_FILE"
DEFAULT_STATE_FILE = "data/smart_devices/tvs.json"
HOST_ENV_TEMPLATE = "TV_{tv_id}_HOST"
ECP_PORT = 8060
REQUEST_TIMEOUT_SECONDS = 3
KEYPRESSES = {
    "power": "PowerOff",
    "volume_up": "VolumeUp",
    "volume_down": "VolumeDown",
    "mute": "VolumeMute",
    "home": "Home",
    "select": "Select",
    "up": "Up",
    "down": "Down",
    "left": "Left",
    "right": "Right",
}


class TVControl:
    """Smart TV power/volume/input via Roku ECP, simulated fallback.
    Use get_tv_control()."""

    def _state_path(self) -> str:
        path = os.environ.get(STATE_FILE_ENV, DEFAULT_STATE_FILE)
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        return path

    def _read_state(self) -> Dict:
        path = self._state_path()
        if not os.path.exists(path):
            return {"tvs": {}}
        with open(path) as fh:
            return json.load(fh)

    def _write_state(self, data: Dict) -> None:
        with open(self._state_path(), "w") as fh:
            json.dump(data, fh)

    def _host_for(self, tv_id: str) -> Optional[str]:
        return os.environ.get(HOST_ENV_TEMPLATE.format(tv_id=tv_id.upper()))

    def is_tv_configured(self, tv_id: str) -> bool:
        """Whether `tv_id` has a real ECP host configured - False
        just means calls for it are simulated-only."""
        return _REQUESTS_AVAILABLE and bool(self._host_for(tv_id))

    def _ecp_post(self, tv_id: str, path: str) -> Optional[Dict]:
        host = self._host_for(tv_id)
        if not host or not _REQUESTS_AVAILABLE:
            return None
        try:
            requests.post(f"http://{host}:{ECP_PORT}{path}", timeout=REQUEST_TIMEOUT_SECONDS)
            return {"ok": True}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def _simulated_set(self, tv_id: str, **fields) -> Dict:
        data = self._read_state()
        entry = data["tvs"].setdefault(tv_id, {"on": False, "volume": 20, "muted": False})
        entry.update({k: v for k, v in fields.items() if v is not None})
        data["tvs"][tv_id] = entry
        self._write_state(data)
        return {"success": True, "simulated": True, "state": entry, "error": None}

    def send_keypress(self, tv_id: str, key: str) -> Dict:
        """Sends one of KEYPRESSES' keys to `tv_id`. Returns
        {"success": bool, "simulated": bool, "error": Optional[str]}."""
        if key not in KEYPRESSES:
            return {"success": False, "simulated": False, "error": f"key must be one of {list(KEYPRESSES)}"}
        result = self._ecp_post(tv_id, f"/keypress/{KEYPRESSES[key]}")
        if result is not None:
            if not result["ok"]:
                return {"success": False, "simulated": False, "error": result["error"]}
            return {"success": True, "simulated": False, "error": None}
        self._simulated_set(tv_id)  # touch the registry so list_tvs() sees it
        return {"success": True, "simulated": True, "error": None}

    def turn_on(self, tv_id: str) -> Dict:
        """Turns `tv_id` on. ECP's PowerOff keypress is a toggle on
        most Roku TVs, so a real device may need a second call if
        already on - this module can't distinguish that without
        querying device state, which ECP's keypress endpoint doesn't
        report. Returns the same shape as send_keypress()."""
        result = self._ecp_post(tv_id, f"/keypress/{KEYPRESSES['power']}")
        if result is not None:
            if not result["ok"]:
                return {"success": False, "simulated": False, "error": result["error"]}
            return {"success": True, "simulated": False, "error": None}
        self._simulated_set(tv_id, on=True)
        return {"success": True, "simulated": True, "error": None}

    def turn_off(self, tv_id: str) -> Dict:
        """See turn_on()'s note on ECP's power keypress being a
        toggle. Returns the same shape as send_keypress()."""
        result = self._ecp_post(tv_id, f"/keypress/{KEYPRESSES['power']}")
        if result is not None:
            if not result["ok"]:
                return {"success": False, "simulated": False, "error": result["error"]}
            return {"success": True, "simulated": False, "error": None}
        self._simulated_set(tv_id, on=False)
        return {"success": True, "simulated": True, "error": None}

    def set_volume(self, tv_id: str, level: int) -> Dict:
        """Sets absolute volume 0-100 by sending repeated
        volume_up/volume_down keypresses from the last known level -
        ECP has no absolute-volume endpoint. On a real TV this is
        only as accurate as the last simulated/tracked level, since
        ECP gives no way to read current volume back. Returns
        {"success": bool, "simulated": bool, "error": Optional[str]}."""
        current = self.get_state(tv_id).get("volume", 20)
        steps = level - current
        key = "volume_up" if steps > 0 else "volume_down"
        for _ in range(abs(steps)):
            result = self._ecp_post(tv_id, f"/keypress/{KEYPRESSES[key]}")
            if result is not None and not result["ok"]:
                return {"success": False, "simulated": False, "error": result["error"]}
        self._simulated_set(tv_id, volume=level)
        return {"success": True, "simulated": not self.is_tv_configured(tv_id), "error": None}

    def launch_app(self, tv_id: str, channel_id: str) -> Dict:
        """Launches Roku channel `channel_id` (a numeric string, e.g.
        Netflix's "12"). Simulated-only if `tv_id` isn't configured -
        there's no meaningful local stand-in for "which app is open".
        Returns {"success": bool, "simulated": bool, "error":
        Optional[str]}."""
        host = self._host_for(tv_id)
        if host and _REQUESTS_AVAILABLE:
            try:
                requests.post(f"http://{host}:{ECP_PORT}/launch/{channel_id}", timeout=REQUEST_TIMEOUT_SECONDS)
                return {"success": True, "simulated": False, "error": None}
            except Exception as exc:
                return {"success": False, "simulated": False, "error": str(exc)}
        self._simulated_set(tv_id, current_app=channel_id)
        return {"success": True, "simulated": True, "error": None}

    def get_state(self, tv_id: str) -> Dict:
        """Last known state for `tv_id` from the simulated registry -
        the one place this module tracks volume/app history
        regardless of whether the TV is real. Returns {"on": bool,
        "volume": int, "muted": bool}."""
        return self._read_state()["tvs"].get(tv_id, {"on": False, "volume": 20, "muted": False})

    def list_tvs(self) -> List[str]:
        """IDs of every TV this module has ever addressed."""
        return list(self._read_state()["tvs"].keys())


_tv_control: Optional[TVControl] = None


def get_tv_control() -> TVControl:
    global _tv_control
    if _tv_control is None:
        _tv_control = TVControl()
    return _tv_control
