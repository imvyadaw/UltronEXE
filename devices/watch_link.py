"""
Watch Link (DEVICES)
========================
Health-metric ingestion and notification forwarding for a paired
smartwatch, mirroring phone_link.py's pair/notify shape but for data
that flows the other direction too: a companion watch app is expected
to push readings (steps, heart rate, battery) into record_reading()
on whatever cadence it likes, and anything above this module reads
them back with get_latest()/get_history() rather than polling a
vendor API this module doesn't have credentials for.

No vendor SDK is assumed (Apple Watch, Wear OS and Garmin all differ
and none expose a plain local API) - record_reading() is the
integration point a phone_link.py-style push receiver or a small
local HTTP endpoint would call into. Notification delivery reuses
phone_link.py's push gateway (PHONE_PUSH_URL/PHONE_PUSH_TOKEN) rather
than inventing a second one, since most watch notifications are
mirrored from the paired phone anyway.
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

STATE_FILE_ENV = "SMART_DEVICES_WATCH_FILE"
DEFAULT_STATE_FILE = "data/smart_devices/watches.json"
PUSH_URL_ENV = "PHONE_PUSH_URL"
PUSH_TOKEN_ENV = "PHONE_PUSH_TOKEN"
REQUEST_TIMEOUT_SECONDS = 3
MAX_HISTORY_PER_WATCH = 500
VALID_METRICS = ("steps", "heart_rate", "battery")


class WatchLink:
    """Watch pairing, health readings, notification forwarding. Use
    get_watch_link()."""

    def _state_path(self) -> str:
        path = os.environ.get(STATE_FILE_ENV, DEFAULT_STATE_FILE)
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        return path

    def _read_state(self) -> Dict:
        path = self._state_path()
        if not os.path.exists(path):
            return {"watches": {}}
        with open(path) as fh:
            return json.load(fh)

    def _write_state(self, data: Dict) -> None:
        with open(self._state_path(), "w") as fh:
            json.dump(data, fh)

    def pair(self, watch_id: str, label: Optional[str] = None) -> Dict:
        """Marks `watch_id` as paired. Returns {"success": bool,
        "error": Optional[str]}."""
        data = self._read_state()
        entry = data["watches"].get(watch_id, {"readings": {}})
        entry.update({"paired": True, "label": label})
        data["watches"][watch_id] = entry
        self._write_state(data)
        return {"success": True, "error": None}

    def is_paired(self, watch_id: str) -> bool:
        return bool(self._read_state()["watches"].get(watch_id, {}).get("paired", False))

    def record_reading(self, watch_id: str, metric: str, value: float) -> Dict:
        """Appends one reading for `metric` (one of VALID_METRICS) at
        the current time. Fails if `watch_id` isn't paired or
        `metric` isn't recognized, since an unbounded metric name
        would make get_latest()/get_history() unreliable for callers
        that expect a fixed set. Returns {"success": bool, "error":
        Optional[str]}."""
        if metric not in VALID_METRICS:
            return {"success": False, "error": f"metric must be one of {VALID_METRICS}"}
        if not self.is_paired(watch_id):
            return {"success": False, "error": f"'{watch_id}' is not paired"}
        data = self._read_state()
        readings = data["watches"][watch_id].setdefault("readings", {}).setdefault(metric, [])
        readings.append({"value": value, "timestamp": time.time()})
        data["watches"][watch_id]["readings"][metric] = readings[-MAX_HISTORY_PER_WATCH:]
        self._write_state(data)
        return {"success": True, "error": None}

    def get_latest(self, watch_id: str, metric: str) -> Optional[Dict]:
        """Most recent {"value": float, "timestamp": float} reading
        for `metric`, or None if no reading has ever been recorded."""
        readings = self._read_state()["watches"].get(watch_id, {}).get("readings", {}).get(metric, [])
        return readings[-1] if readings else None

    def get_history(self, watch_id: str, metric: str, limit: int = 50) -> List[Dict]:
        """Up to `limit` most recent readings for `metric`, oldest
        first."""
        readings = self._read_state()["watches"].get(watch_id, {}).get("readings", {}).get(metric, [])
        return readings[-limit:]

    def notify(self, watch_id: str, title: str, message: str) -> Dict:
        """Sends a notification to `watch_id`, reusing the same push
        gateway as phone_link.py. Delivered immediately if
        PHONE_PUSH_URL is configured and reachable; otherwise reported
        as undelivered rather than queued, since a watch notification
        that's minutes late is rarely still useful. Returns
        {"success": bool, "delivered": bool, "error": Optional[str]}."""
        if not self.is_paired(watch_id):
            return {"success": False, "delivered": False, "error": f"'{watch_id}' is not paired"}
        if not (_REQUESTS_AVAILABLE and os.environ.get(PUSH_URL_ENV)):
            return {"success": True, "delivered": False, "error": None}
        try:
            requests.post(
                os.environ[PUSH_URL_ENV],
                json={"to": watch_id, "title": title, "message": message, "timestamp": time.time()},
                headers={"Authorization": f"Bearer {os.environ.get(PUSH_TOKEN_ENV, '')}"},
                timeout=REQUEST_TIMEOUT_SECONDS,
            )
            return {"success": True, "delivered": True, "error": None}
        except Exception as exc:
            return {"success": True, "delivered": False, "error": str(exc)}

    def list_watches(self) -> List[str]:
        """IDs of every watch this module has ever paired."""
        return list(self._read_state()["watches"].keys())


_watch_link: Optional[WatchLink] = None


def get_watch_link() -> WatchLink:
    global _watch_link
    if _watch_link is None:
        _watch_link = WatchLink()
    return _watch_link
