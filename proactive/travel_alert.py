"""
Travel Alert (PROACTIVE)
============================
A trip registry with a window check, not a travel-conditions sensor -
this module has no idea about actual traffic, weather, or flight
status; register_trip() takes whatever a caller already knows
(destination, an ISO departure timestamp, mode), and check_alerts()
returns which registered trips fall within ALERT_WINDOW_HOURS of now
and haven't been marked alerted yet, so a caller doesn't have to
re-scan the whole registry itself every time it polls. Actually
notifying anyone is left to the caller; mark_alerted() just stops the
same trip from showing up in check_alerts() again.

One optional integration: if PHASE_18_9_1_AI_EVOLUTION's
danger_sense.py is importable, check_alerts() can register a
low-severity "travel:<trip_id>" signal for each trip it surfaces, via
`notify_danger_sense=True`, purely as a convenience so an upcoming
trip shows up in a caller's overall risk picture too. The import is
guarded and the parameter defaults to False, so this module works
identically without 18.9.1 present.
"""

import json
import os
import time
from typing import Dict, List, Optional

try:
    from predict.danger_sense import get_danger_sense

    _DANGER_SENSE_AVAILABLE = True
except Exception:
    _DANGER_SENSE_AVAILABLE = False

STATE_FILE_ENV = "SELF_MANAGEMENT_TRAVEL_ALERT_FILE"
DEFAULT_STATE_FILE = "data/self_management/travel_alert.json"
ALERT_WINDOW_HOURS = 24


class TravelAlert:
    """Trip registry and alert-window check. Use get_travel_alert()."""

    def _state_path(self) -> str:
        path = os.environ.get(STATE_FILE_ENV, DEFAULT_STATE_FILE)
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        return path

    def _read_state(self) -> Dict:
        path = self._state_path()
        if not os.path.exists(path):
            return {"trips": {}}
        with open(path) as fh:
            return json.load(fh)

    def _write_state(self, data: Dict) -> None:
        with open(self._state_path(), "w") as fh:
            json.dump(data, fh)

    def register_trip(self, trip_id: str, destination: str, depart_time: float, mode: str = "") -> Dict:
        """Registers `trip_id` with `destination`, `depart_time`
        (Unix timestamp) and an optional `mode` (e.g. "flight",
        "train"). Re-registering an existing trip_id overwrites its
        details and resets its "alerted" flag. Returns {"success":
        bool, "error": Optional[str]}."""
        if not trip_id or not destination:
            return {"success": False, "error": "trip_id and destination required"}
        data = self._read_state()
        data["trips"][trip_id] = {
            "destination": destination,
            "depart_time": depart_time,
            "mode": mode,
            "alerted": False,
        }
        self._write_state(data)
        return {"success": True, "error": None}

    def check_alerts(self, within_hours: float = ALERT_WINDOW_HOURS, notify_danger_sense: bool = False) -> List[Dict]:
        """Every registered, not-yet-alerted trip departing within
        `within_hours` of now, soonest first, as {"trip_id": str,
        "destination": str, "depart_time": float, "mode": str}. If
        `notify_danger_sense` is True and
        predict.danger_sense is importable,
        also registers a severity-1 "travel:<trip_id>" signal there
        for each trip returned - silently skipped if that module
        isn't available. Does not mark anything alerted itself; call
        mark_alerted() once the caller has actually notified
        someone."""
        now = time.time()
        cutoff = now + within_hours * 3600
        data = self._read_state()["trips"]
        matches = [
            {"trip_id": tid, "destination": t["destination"], "depart_time": t["depart_time"], "mode": t["mode"]}
            for tid, t in data.items()
            if not t["alerted"] and now <= t["depart_time"] <= cutoff
        ]
        matches.sort(key=lambda m: m["depart_time"])
        if notify_danger_sense and _DANGER_SENSE_AVAILABLE:
            sense = get_danger_sense()
            for m in matches:
                sense.register_signal(f"travel:{m['trip_id']}", severity=1)
        return matches

    def mark_alerted(self, trip_id: str) -> Dict:
        """Marks `trip_id` as alerted so it stops appearing in
        check_alerts(). Returns {"success": bool, "error":
        Optional[str]}; fails if trip_id isn't registered."""
        data = self._read_state()
        if trip_id not in data["trips"]:
            return {"success": False, "error": "trip not registered"}
        data["trips"][trip_id]["alerted"] = True
        self._write_state(data)
        return {"success": True, "error": None}

    def list_trips(self) -> List[Dict]:
        """Every registered trip, soonest departure first, regardless
        of alert status."""
        data = self._read_state()["trips"]
        trips = [{"trip_id": tid, **t} for tid, t in data.items()]
        trips.sort(key=lambda t: t["depart_time"])
        return trips


_travel_alert: Optional[TravelAlert] = None


def get_travel_alert() -> TravelAlert:
    global _travel_alert
    if _travel_alert is None:
        _travel_alert = TravelAlert()
    return _travel_alert
