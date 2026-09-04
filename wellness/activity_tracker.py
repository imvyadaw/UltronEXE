"""Activity tracker
===================
Local, JSON-backed log of steps, water intake, sleep hours, workouts, and
a simple 1-5 mood check-in. Same persistence shape as
finance/expense_tracker.py - a flat list of dated entries, human-readable
and editable.

Nothing here is a wearable/health-app integration - it's a plain log the
user (or a voice command) tells Ultron about, same "Ultron tracks, it
doesn't measure" relationship expense_tracker.py has with money.
"""

import json
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional

from core.logger import get_logger

logger = get_logger("ultron.wellness.activity")

DATA_PATH = Path(__file__).resolve().parents[1] / "storage" / "wellness" / "activity.json"

VALID_KINDS = {"steps", "water_ml", "sleep_hours", "workout", "mood"}


def _today() -> str:
    return datetime.now(timezone.utc).astimezone().date().isoformat()


class ActivityTracker:
    def __init__(self):
        self._entries: List[Dict] = self._load()

    # -- persistence ------------------------------------------------
    def _load(self) -> List[Dict]:
        try:
            if DATA_PATH.exists():
                return json.loads(DATA_PATH.read_text(encoding="utf-8"))
        except Exception:
            logger.exception("activity_tracker: state load failed, starting fresh")
        return []

    def _save(self) -> None:
        try:
            DATA_PATH.parent.mkdir(parents=True, exist_ok=True)
            DATA_PATH.write_text(json.dumps(self._entries, indent=2), encoding="utf-8")
        except Exception:
            logger.exception("activity_tracker: state save failed")

    def _log(self, kind: str, value: Dict, date: Optional[str] = None) -> Dict:
        entry = {
            "id": uuid.uuid4().hex[:8],
            "kind": kind,
            "date": date or _today(),
            "timestamp": time.time(),
            **value,
        }
        self._entries.append(entry)
        self._save()
        return entry

    # -- writes -------------------------------------------------------
    def log_steps(self, count: int, date: Optional[str] = None) -> Dict:
        try:
            count = int(count)
        except (TypeError, ValueError):
            return {"success": False, "error": f"invalid step count: {count!r}"}
        if count < 0:
            return {"success": False, "error": "step count can't be negative"}
        return {"success": True, "entry": self._log("steps", {"count": count}, date)}

    def log_water(self, ml: float, date: Optional[str] = None) -> Dict:
        try:
            ml = float(ml)
        except (TypeError, ValueError):
            return {"success": False, "error": f"invalid water amount: {ml!r}"}
        if ml <= 0:
            return {"success": False, "error": "water amount must be positive"}
        return {"success": True, "entry": self._log("water_ml", {"ml": ml}, date)}

    def log_sleep(self, hours: float, date: Optional[str] = None) -> Dict:
        try:
            hours = float(hours)
        except (TypeError, ValueError):
            return {"success": False, "error": f"invalid sleep hours: {hours!r}"}
        if not (0 < hours <= 24):
            return {"success": False, "error": "sleep hours must be between 0 and 24"}
        return {"success": True, "entry": self._log("sleep_hours", {"hours": hours}, date)}

    def log_workout(self, workout_type: str, duration_min: float, notes: str = "", date: Optional[str] = None) -> Dict:
        workout_type = (workout_type or "").strip() or "workout"
        try:
            duration_min = float(duration_min)
        except (TypeError, ValueError):
            return {"success": False, "error": f"invalid duration: {duration_min!r}"}
        if duration_min <= 0:
            return {"success": False, "error": "duration must be positive"}
        return {
            "success": True,
            "entry": self._log(
                "workout", {"workout_type": workout_type, "duration_min": duration_min, "notes": notes}, date
            ),
        }

    def log_mood(self, score: int, note: str = "", date: Optional[str] = None) -> Dict:
        try:
            score = int(score)
        except (TypeError, ValueError):
            return {"success": False, "error": f"invalid mood score: {score!r}"}
        if not (1 <= score <= 5):
            return {"success": False, "error": "mood score must be 1-5"}
        return {"success": True, "entry": self._log("mood", {"score": score, "note": note}, date)}

    # -- reads ----------------------------------------------------------
    def entries_for_date(self, date: str) -> List[Dict]:
        return [e for e in self._entries if e["date"] == date]

    def daily_summary(self, date: Optional[str] = None) -> Dict:
        date = date or _today()
        day_entries = self.entries_for_date(date)
        steps = sum(e["count"] for e in day_entries if e["kind"] == "steps")
        water_ml = sum(e["ml"] for e in day_entries if e["kind"] == "water_ml")
        sleep_hours = sum(e["hours"] for e in day_entries if e["kind"] == "sleep_hours")
        workouts = [e for e in day_entries if e["kind"] == "workout"]
        moods = [e["score"] for e in day_entries if e["kind"] == "mood"]

        return {
            "success": True,
            "date": date,
            "steps": steps,
            "water_ml": round(water_ml, 1),
            "sleep_hours": round(sleep_hours, 2),
            "workout_count": len(workouts),
            "workout_minutes": round(sum(w["duration_min"] for w in workouts), 1),
            "avg_mood": round(sum(moods) / len(moods), 2) if moods else None,
        }

    def weekly_summary(self) -> Dict:
        today = datetime.now(timezone.utc).astimezone().date()
        days = [(today - timedelta(days=i)).isoformat() for i in range(6, -1, -1)]
        daily = [self.daily_summary(d) for d in days]
        return {
            "success": True,
            "days": daily,
            "total_steps": sum(d["steps"] for d in daily),
            "total_water_ml": round(sum(d["water_ml"] for d in daily), 1),
            "total_sleep_hours": round(sum(d["sleep_hours"] for d in daily), 2),
            "total_workouts": sum(d["workout_count"] for d in daily),
        }


_activity_tracker: Optional[ActivityTracker] = None


def get_activity_tracker() -> ActivityTracker:
    global _activity_tracker
    if _activity_tracker is None:
        _activity_tracker = ActivityTracker()
    return _activity_tracker
