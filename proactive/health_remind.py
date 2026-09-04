"""
Health Remind (PROACTIVE)
=============================
A generic interval-reminder scheduler, not a source of health advice
- this module has no built-in notion of what "should" be reminded
about. register_reminder() takes a caller-chosen `label` (whatever
the caller wants to be reminded of - "water", "stretch break", a
specific appointment) and an `interval_hours`; due_reminders() just
does arithmetic on elapsed time since the label was last
acknowledged. Nothing here generates, suggests, or evaluates medical
content - nor should a caller expect it to; this is scheduling
plumbing only, mirroring PREDICT/need_before.py's caller-supplies-the-
meaning approach rather than PHASE_18_9_1_AI_EVOLUTION's
mood_predict.py, which explicitly disclaims being a clinical signal.
"""

import json
import os
import time
from typing import Dict, List, Optional

STATE_FILE_ENV = "SELF_MANAGEMENT_HEALTH_REMIND_FILE"
DEFAULT_STATE_FILE = "data/self_management/health_remind.json"


class HealthRemind:
    """Generic interval-reminder scheduler over caller-supplied
    labels. Use get_health_remind(). Stores no medical content of its
    own."""

    def _state_path(self) -> str:
        path = os.environ.get(STATE_FILE_ENV, DEFAULT_STATE_FILE)
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        return path

    def _read_state(self) -> Dict:
        path = self._state_path()
        if not os.path.exists(path):
            return {"reminders": {}}
        with open(path) as fh:
            return json.load(fh)

    def _write_state(self, data: Dict) -> None:
        with open(self._state_path(), "w") as fh:
            json.dump(data, fh)

    def register_reminder(self, reminder_id: str, label: str, interval_hours: float) -> Dict:
        """Registers `reminder_id` with a caller-chosen `label` (used
        verbatim, never interpreted) that's due every
        `interval_hours`, starting from registration time.
        Re-registering an existing reminder_id overwrites its label
        and interval but keeps its last-acknowledged time. Returns
        {"success": bool, "error": Optional[str]}."""
        if not reminder_id or not label or interval_hours <= 0:
            return {"success": False, "error": "reminder_id, label, and a positive interval_hours are required"}
        data = self._read_state()
        existing = data["reminders"].get(reminder_id)
        last_ack = existing["last_ack"] if existing else time.time()
        data["reminders"][reminder_id] = {"label": label, "interval_hours": interval_hours, "last_ack": last_ack}
        self._write_state(data)
        return {"success": True, "error": None}

    def acknowledge(self, reminder_id: str) -> Dict:
        """Resets `reminder_id`'s timer to now, as if the caller just
        handled it. Returns {"success": bool, "error":
        Optional[str]}; fails if reminder_id isn't registered."""
        data = self._read_state()
        if reminder_id not in data["reminders"]:
            return {"success": False, "error": "reminder not registered"}
        data["reminders"][reminder_id]["last_ack"] = time.time()
        self._write_state(data)
        return {"success": True, "error": None}

    def due_reminders(self) -> List[Dict]:
        """Every reminder whose interval has elapsed since its last
        acknowledgement, most-overdue first. Returns a list of
        {"reminder_id": str, "label": str, "hours_overdue": float}.
        Calling this does not itself acknowledge anything."""
        now = time.time()
        data = self._read_state()["reminders"]
        due = []
        for rid, r in data.items():
            elapsed_hours = (now - r["last_ack"]) / 3600
            if elapsed_hours >= r["interval_hours"]:
                due.append(
                    {
                        "reminder_id": rid,
                        "label": r["label"],
                        "hours_overdue": round(elapsed_hours - r["interval_hours"], 2),
                    }
                )
        due.sort(key=lambda d: d["hours_overdue"], reverse=True)
        return due

    def list_reminders(self) -> List[Dict]:
        """Every registered reminder regardless of due status, as
        {"reminder_id": str, "label": str, "interval_hours": float}."""
        data = self._read_state()["reminders"]
        return [
            {"reminder_id": rid, "label": r["label"], "interval_hours": r["interval_hours"]} for rid, r in data.items()
        ]

    def remove_reminder(self, reminder_id: str) -> Dict:
        """Unregisters `reminder_id` entirely. Returns {"success":
        bool, "error": Optional[str]}."""
        data = self._read_state()
        if reminder_id not in data["reminders"]:
            return {"success": False, "error": "reminder not registered"}
        del data["reminders"][reminder_id]
        self._write_state(data)
        return {"success": True, "error": None}


_health_remind: Optional[HealthRemind] = None


def get_health_remind() -> HealthRemind:
    global _health_remind
    if _health_remind is None:
        _health_remind = HealthRemind()
    return _health_remind
