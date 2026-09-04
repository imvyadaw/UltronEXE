"""
Evening Wrap (PROACTIVE)
============================
morning_brief.py's counterpart for the end of the day: log_event()
lets any caller record one thing that happened today, tagged
"done"/"pending"/"note", and generate_wrap() tallies the day into
counts plus the raw list, in caller-registration order. Like
morning_brief.py, this module has no opinion about what counts as a
noteworthy event - it only tallies and returns what's been logged for
the date in question.
"""

import json
import os
import time
from datetime import date as _date
from typing import Dict, Optional

STATE_FILE_ENV = "SELF_MANAGEMENT_EVENING_WRAP_FILE"
DEFAULT_STATE_FILE = "data/self_management/evening_wrap.json"
VALID_KINDS = ("done", "pending", "note")


class EveningWrap:
    """End-of-day event log and tally. Use get_evening_wrap()."""

    def _state_path(self) -> str:
        path = os.environ.get(STATE_FILE_ENV, DEFAULT_STATE_FILE)
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        return path

    def _read_state(self) -> Dict:
        path = self._state_path()
        if not os.path.exists(path):
            return {"events": []}
        with open(path) as fh:
            return json.load(fh)

    def _write_state(self, data: Dict) -> None:
        with open(self._state_path(), "w") as fh:
            json.dump(data, fh)

    def log_event(self, text: str, kind: str = "note", for_date: Optional[str] = None) -> Dict:
        """Records `text` under `kind` ("done"/"pending"/"note") for
        `for_date` (ISO "YYYY-MM-DD", defaults to today). Returns
        {"success": bool, "error": Optional[str]}."""
        if not text:
            return {"success": False, "error": "text required"}
        if kind not in VALID_KINDS:
            return {"success": False, "error": f"kind must be one of {VALID_KINDS}"}
        target_date = for_date or _date.today().isoformat()
        data = self._read_state()
        data["events"].append({"text": text, "kind": kind, "date": target_date, "timestamp": time.time()})
        self._write_state(data)
        return {"success": True, "error": None}

    def generate_wrap(self, for_date: Optional[str] = None) -> Dict:
        """Tallies every event logged for `for_date` (defaults to
        today) into counts per kind plus the events themselves in
        the order they were logged. Returns {"date": str, "counts":
        {"done": int, "pending": int, "note": int}, "events":
        [{"text": str, "kind": str}, ...], "error": Optional[str]}."""
        target_date = for_date or _date.today().isoformat()
        events = [e for e in self._read_state()["events"] if e["date"] == target_date]
        counts = {kind: sum(1 for e in events if e["kind"] == kind) for kind in VALID_KINDS}
        return {
            "date": target_date,
            "counts": counts,
            "events": [{"text": e["text"], "kind": e["kind"]} for e in events],
            "error": None,
        }

    def carry_over_pending(self, from_date: str, to_date: Optional[str] = None) -> Dict:
        """Re-logs every "pending" event from `from_date` under
        `to_date` (defaults to today) unchanged, so an unfinished
        item doesn't just vanish at day's end. Does not remove the
        originals from `from_date` - the wrap for that day still
        shows what was pending on it. Returns {"success": bool,
        "carried": int, "error": Optional[str]}."""
        target_date = to_date or _date.today().isoformat()
        events = [e for e in self._read_state()["events"] if e["date"] == from_date and e["kind"] == "pending"]
        for e in events:
            self.log_event(e["text"], kind="pending", for_date=target_date)
        return {"success": True, "carried": len(events), "error": None}


_evening_wrap: Optional[EveningWrap] = None


def get_evening_wrap() -> EveningWrap:
    global _evening_wrap
    if _evening_wrap is None:
        _evening_wrap = EveningWrap()
    return _evening_wrap
