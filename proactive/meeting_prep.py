"""
Meeting Prep (PROACTIVE)
============================
A meeting registry plus a prep-notes scratchpad, not a calendar sync
and not a note generator - register_meeting() takes whatever a caller
already knows about a meeting (title, ISO timestamp, attendee list),
and add_prep_note() lets anything (a person, from_habit.py noticing
this attendee always needs the same doc, next_action.py) add one line
of prep for it. get_prep() hands back everything filed for a meeting;
upcoming() filters the registry to what's starting within a
caller-given window, for a "what do I need to prep for soon" query.
"""

import json
import os
import time
from typing import Dict, List, Optional

STATE_FILE_ENV = "SELF_MANAGEMENT_MEETING_PREP_FILE"
DEFAULT_STATE_FILE = "data/self_management/meeting_prep.json"


class MeetingPrep:
    """Meeting registry and prep-notes scratchpad. Use
    get_meeting_prep()."""

    def _state_path(self) -> str:
        path = os.environ.get(STATE_FILE_ENV, DEFAULT_STATE_FILE)
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        return path

    def _read_state(self) -> Dict:
        path = self._state_path()
        if not os.path.exists(path):
            return {"meetings": {}}
        with open(path) as fh:
            return json.load(fh)

    def _write_state(self, data: Dict) -> None:
        with open(self._state_path(), "w") as fh:
            json.dump(data, fh)

    def register_meeting(
        self, meeting_id: str, title: str, start_time: float, attendees: Optional[List[str]] = None
    ) -> Dict:
        """Registers `meeting_id` with `title`, `start_time` (Unix
        timestamp) and an optional `attendees` list. Re-registering
        an existing meeting_id overwrites its details but keeps any
        prep notes already filed against it. Returns {"success":
        bool, "error": Optional[str]}."""
        if not meeting_id or not title:
            return {"success": False, "error": "meeting_id and title required"}
        data = self._read_state()
        existing = data["meetings"].get(meeting_id, {"notes": []})
        data["meetings"][meeting_id] = {
            "title": title,
            "start_time": start_time,
            "attendees": attendees or [],
            "notes": existing["notes"],
        }
        self._write_state(data)
        return {"success": True, "error": None}

    def add_prep_note(self, meeting_id: str, note: str) -> Dict:
        """Appends one line of prep to a registered meeting. Returns
        {"success": bool, "error": Optional[str]}; fails if
        meeting_id hasn't been registered yet."""
        if not note:
            return {"success": False, "error": "note required"}
        data = self._read_state()
        if meeting_id not in data["meetings"]:
            return {"success": False, "error": "meeting not registered"}
        data["meetings"][meeting_id]["notes"].append({"note": note, "timestamp": time.time()})
        self._write_state(data)
        return {"success": True, "error": None}

    def get_prep(self, meeting_id: str) -> Optional[Dict]:
        """Everything filed for `meeting_id`: {"title": str,
        "start_time": float, "attendees": List[str], "notes":
        List[str]} (notes in the order they were added), or None if
        it hasn't been registered."""
        meeting = self._read_state()["meetings"].get(meeting_id)
        if meeting is None:
            return None
        return {
            "title": meeting["title"],
            "start_time": meeting["start_time"],
            "attendees": meeting["attendees"],
            "notes": [n["note"] for n in meeting["notes"]],
        }

    def upcoming(self, within_hours: float = 24) -> List[Dict]:
        """Every registered meeting starting between now and
        `within_hours` from now, soonest first. Returns a list of
        {"meeting_id": str, "title": str, "start_time": float}.
        Meetings already in the past are excluded."""
        now = time.time()
        cutoff = now + within_hours * 3600
        data = self._read_state()["meetings"]
        matches = [
            {"meeting_id": mid, "title": m["title"], "start_time": m["start_time"]}
            for mid, m in data.items()
            if now <= m["start_time"] <= cutoff
        ]
        matches.sort(key=lambda m: m["start_time"])
        return matches


_meeting_prep: Optional[MeetingPrep] = None


def get_meeting_prep() -> MeetingPrep:
    global _meeting_prep
    if _meeting_prep is None:
        _meeting_prep = MeetingPrep()
    return _meeting_prep
