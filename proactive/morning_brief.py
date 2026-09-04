"""
Morning Brief (PROACTIVE)
=============================
A same-day compiler, not a content generator - this module never
decides what belongs in a brief. add_item() lets any caller (a
calendar sync, meeting_prep.py, travel_alert.py, health_remind.py, a
person) file one line of text under a section for a given date, and
generate_brief() gathers everything filed for today (or a given date)
into one ordered structure by priority, highest first within each
section. What the sections are called, how many there are, and what
the text says are entirely up to callers - this module just holds and
orders whatever it's given.
"""

import json
import os
import time
from datetime import date as _date
from typing import Dict, List, Optional

STATE_FILE_ENV = "SELF_MANAGEMENT_MORNING_BRIEF_FILE"
DEFAULT_STATE_FILE = "data/self_management/morning_brief.json"


class MorningBrief:
    """Same-day item compiler. Use get_morning_brief()."""

    def _state_path(self) -> str:
        path = os.environ.get(STATE_FILE_ENV, DEFAULT_STATE_FILE)
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        return path

    def _read_state(self) -> Dict:
        path = self._state_path()
        if not os.path.exists(path):
            return {"items": []}
        with open(path) as fh:
            return json.load(fh)

    def _write_state(self, data: Dict) -> None:
        with open(self._state_path(), "w") as fh:
            json.dump(data, fh)

    def add_item(self, section: str, text: str, priority: int = 0, for_date: Optional[str] = None) -> Dict:
        """Files `text` under `section` for `for_date` (ISO
        "YYYY-MM-DD", defaults to today), ranked within that section
        by `priority` (higher surfaces first in generate_brief()).
        Returns {"success": bool, "error": Optional[str]}."""
        if not section or not text:
            return {"success": False, "error": "section and text required"}
        target_date = for_date or _date.today().isoformat()
        data = self._read_state()
        data["items"].append(
            {
                "section": section,
                "text": text,
                "priority": priority,
                "date": target_date,
                "timestamp": time.time(),
            }
        )
        self._write_state(data)
        return {"success": True, "error": None}

    def generate_brief(self, for_date: Optional[str] = None) -> Dict:
        """Every item filed for `for_date` (defaults to today),
        grouped by section and sorted highest-priority first within
        each. Returns {"date": str, "sections": {section: [text,
        ...]}, "error": Optional[str]}. An empty "sections" dict
        means nothing's been filed for that date yet."""
        target_date = for_date or _date.today().isoformat()
        items = [i for i in self._read_state()["items"] if i["date"] == target_date]
        items.sort(key=lambda i: i["priority"], reverse=True)
        sections: Dict[str, List[str]] = {}
        for item in items:
            sections.setdefault(item["section"], []).append(item["text"])
        return {"date": target_date, "sections": sections, "error": None}

    def clear_date(self, for_date: Optional[str] = None) -> Dict:
        """Drops every item filed for `for_date` (defaults to
        today). Returns {"success": bool, "removed": int, "error":
        Optional[str]}."""
        target_date = for_date or _date.today().isoformat()
        data = self._read_state()
        before = len(data["items"])
        data["items"] = [i for i in data["items"] if i["date"] != target_date]
        removed = before - len(data["items"])
        self._write_state(data)
        return {"success": True, "removed": removed, "error": None}


_morning_brief: Optional[MorningBrief] = None


def get_morning_brief() -> MorningBrief:
    global _morning_brief
    if _morning_brief is None:
        _morning_brief = MorningBrief()
    return _morning_brief
