"""
Phone Link (DEVICES)
========================
Pairing state and notification forwarding for a paired phone. There's
no single API a "phone" exposes the way Hue exposes bulbs, so this
assumes the companion side is a push gateway this project's own
CONNECT/*.py-style credentials point at (PHONE_PUSH_URL,
PHONE_PUSH_TOKEN) - a self-hosted or ntfy.sh-style endpoint that
accepts a plain POST. Without both configured, or without `requests`,
notify() still succeeds and just queues the message locally instead
of delivering it, so callers never have to check availability first.

Pairing itself (scanning a QR code, confirming on the phone) is out
of scope here, same as light_control.py doesn't handle Hue bridge
button-press pairing - this module only tracks whether a phone_id has
ever been marked paired via pair(), and lets notify()/get_status()
work the same regardless.
"""

import json
import os
import time
from typing import Dict, List, Optional

try:
    import requests

    _REQUESTS_AVAILABLE = True
except Exception:
    _REQUESTS_AVAILABLE = False

STATE_FILE_ENV = "SMART_DEVICES_PHONE_FILE"
DEFAULT_STATE_FILE = "data/smart_devices/phones.json"
PUSH_URL_ENV = "PHONE_PUSH_URL"
PUSH_TOKEN_ENV = "PHONE_PUSH_TOKEN"
REQUEST_TIMEOUT_SECONDS = 3
MAX_QUEUED_PER_PHONE = 50


class PhoneLink:
    """Phone pairing + notification forwarding. Use get_phone_link()."""

    def _state_path(self) -> str:
        path = os.environ.get(STATE_FILE_ENV, DEFAULT_STATE_FILE)
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        return path

    def _read_state(self) -> Dict:
        path = self._state_path()
        if not os.path.exists(path):
            return {"phones": {}}
        with open(path) as fh:
            return json.load(fh)

    def _write_state(self, data: Dict) -> None:
        with open(self._state_path(), "w") as fh:
            json.dump(data, fh)

    def is_push_configured(self) -> bool:
        """Whether a real push gateway can be reached - False just
        means notify() queues locally instead of delivering."""
        return _REQUESTS_AVAILABLE and bool(os.environ.get(PUSH_URL_ENV))

    def pair(self, phone_id: str, label: Optional[str] = None) -> Dict:
        """Marks `phone_id` as paired. `label` is a free-text display
        name (e.g. "Alex's iPhone"). Returns {"success": bool,
        "error": Optional[str]}."""
        data = self._read_state()
        data["phones"][phone_id] = data["phones"].get(phone_id, {})
        data["phones"][phone_id].update(
            {"paired": True, "label": label, "queue": data["phones"][phone_id].get("queue", [])}
        )
        self._write_state(data)
        return {"success": True, "error": None}

    def unpair(self, phone_id: str) -> Dict:
        """Marks `phone_id` as no longer paired without deleting its
        history. Returns {"success": bool, "error": Optional[str]}."""
        data = self._read_state()
        if phone_id not in data["phones"]:
            return {"success": False, "error": f"'{phone_id}' was never paired"}
        data["phones"][phone_id]["paired"] = False
        self._write_state(data)
        return {"success": True, "error": None}

    def is_paired(self, phone_id: str) -> bool:
        return bool(self._read_state()["phones"].get(phone_id, {}).get("paired", False))

    def notify(self, phone_id: str, title: str, message: str) -> Dict:
        """Sends a notification to `phone_id`. Delivered immediately
        via PHONE_PUSH_URL if configured and reachable; otherwise
        queued locally (get_queued() returns it) so it isn't
        silently lost. Fails only if `phone_id` was never paired.
        Returns {"success": bool, "delivered": bool, "error":
        Optional[str]}."""
        if not self.is_paired(phone_id):
            return {"success": False, "delivered": False, "error": f"'{phone_id}' is not paired"}

        entry = {"title": title, "message": message, "timestamp": time.time()}
        if self.is_push_configured():
            try:
                requests.post(
                    os.environ[PUSH_URL_ENV],
                    json={"to": phone_id, **entry},
                    headers={"Authorization": f"Bearer {os.environ.get(PUSH_TOKEN_ENV, '')}"},
                    timeout=REQUEST_TIMEOUT_SECONDS,
                )
                return {"success": True, "delivered": True, "error": None}
            except Exception:
                from core.error_trace import log_swallowed as _lsw

                _lsw("devices.phone_link.notify")

        data = self._read_state()
        queue = data["phones"][phone_id].setdefault("queue", [])
        queue.append(entry)
        data["phones"][phone_id]["queue"] = queue[-MAX_QUEUED_PER_PHONE:]
        self._write_state(data)
        return {"success": True, "delivered": False, "error": None}

    def get_queued(self, phone_id: str, clear: bool = True) -> List[Dict]:
        """Notifications queued for `phone_id` because push wasn't
        configured/reachable at send time. Clears the queue after
        reading unless `clear` is False."""
        data = self._read_state()
        queue = data["phones"].get(phone_id, {}).get("queue", [])
        if clear and phone_id in data["phones"]:
            data["phones"][phone_id]["queue"] = []
            self._write_state(data)
        return queue

    def list_phones(self) -> List[str]:
        """IDs of every phone this module has ever paired."""
        return list(self._read_state()["phones"].keys())


_phone_link: Optional[PhoneLink] = None


def get_phone_link() -> PhoneLink:
    global _phone_link
    if _phone_link is None:
        _phone_link = PhoneLink()
    return _phone_link
