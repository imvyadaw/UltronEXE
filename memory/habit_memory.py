"""
Habit Memory
============
consciousness.py already logs a rolling introspection trail and
personality.py's `proactiveness` trait already governs *how eagerly*
Ultron surfaces unprompted suggestions - neither one asks *what*
Ultron should proactively suggest. habit_memory.py is that missing
input: a plain, timestamped log of user actions, mined for repeated
action + time-of-day + day-of-week patterns above a minimum occurrence
count. Nothing here triggers a suggestion itself - it only answers
"has this actually happened enough times to call it a habit", leaving
the decision of whether/when to act on that to whatever proactive/
module or COMMAND/control_panel.py chooses to consult it.

Detection is a plain groupby-and-count over (action, hour-bucket,
weekday), not a learned model - matches every other "cheap heuristic
over ML" choice already made in this phase (decision_maker.py's
_estimate_actions, place_memory.py's exact/radius match). Hour is
bucketed to HOUR_BUCKET_WIDTH so "opened Spotify at 9:02" and "9:07"
count as the same habit instance instead of two near-misses.
"""

import sqlite3
import time
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

DB_PATH = Path(__file__).resolve().parents[1] / "storage" / "sqlite" / "habit_memory.db"
HOUR_BUCKET_WIDTH = 2  # 2-hour buckets: 8-10am, 10am-12pm, etc.
DEFAULT_MIN_OCCURRENCES = 3


class HabitMemory:
    """Timestamped action log + simple recurring-pattern detection.
    Use get_habit_memory()."""

    def __init__(self):
        self._db_ok = True
        try:
            DB_PATH.parent.mkdir(parents=True, exist_ok=True)
            self._conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
            self._conn.execute("""CREATE TABLE IF NOT EXISTS actions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    action TEXT, context TEXT, hour_bucket INTEGER, weekday INTEGER, logged_at REAL
                )""")
            self._conn.commit()
        except Exception:
            self._db_ok = False
            self._fallback: List[Dict] = []

    def record_action(self, action: str, context: Optional[str] = None, when: Optional[float] = None) -> None:
        ts = when if when is not None else time.time()
        dt = datetime.fromtimestamp(ts)
        hour_bucket = dt.hour // HOUR_BUCKET_WIDTH
        weekday = dt.weekday()
        if not self._db_ok:
            self._fallback.append(
                {"action": action, "context": context, "hour_bucket": hour_bucket, "weekday": weekday, "logged_at": ts}
            )
            return
        self._conn.execute(
            "INSERT INTO actions (action, context, hour_bucket, weekday, logged_at) VALUES (?, ?, ?, ?, ?)",
            (action, context, hour_bucket, weekday, ts),
        )
        self._conn.commit()

    def _rows(self) -> List[Dict]:
        if not self._db_ok:
            return self._fallback
        cur = self._conn.cursor()
        cur.execute("SELECT action, context, hour_bucket, weekday, logged_at FROM actions")
        cols = ["action", "context", "hour_bucket", "weekday", "logged_at"]
        return [dict(zip(cols, row)) for row in cur.fetchall()]

    def detected_habits(self, min_occurrences: int = DEFAULT_MIN_OCCURRENCES) -> List[Dict]:
        """Groups logged actions by (action, hour_bucket, weekday) and
        returns groups meeting min_occurrences, sorted most-frequent
        first. `weekday` of -1 in the result means "any day" - a
        secondary pass that ignores weekday, for actions that recur
        daily rather than on one specific day of the week."""
        rows = self._rows()
        by_day = Counter((r["action"], r["hour_bucket"], r["weekday"]) for r in rows)
        by_any_day = Counter((r["action"], r["hour_bucket"]) for r in rows)

        habits = []
        best_by_day: Dict = {}  # (action, hour_bucket) -> strongest per-weekday count seen
        for (action, hour_bucket, weekday), count in by_day.items():
            if count >= min_occurrences:
                habits.append(
                    {
                        "action": action,
                        "hour_bucket": hour_bucket,
                        "weekday": weekday,
                        "occurrences": count,
                        "confidence": self._confidence(count),
                    }
                )
            key = (action, hour_bucket)
            best_by_day[key] = max(best_by_day.get(key, 0), count)

        for (action, hour_bucket), count in by_any_day.items():
            # Only skip the aggregate when it adds no new information over
            # the strongest same-weekday split already found - i.e. every
            # occurrence fell on one weekday. Otherwise the aggregate is
            # the *stronger* signal (a daily habit split thin across
            # several weekdays) and must not be shadowed by weaker
            # per-weekday entries, or a low min_occurrences call (like
            # habit_confidence's) would understate confidence.
            if count >= min_occurrences and count > best_by_day.get((action, hour_bucket), 0):
                habits.append(
                    {
                        "action": action,
                        "hour_bucket": hour_bucket,
                        "weekday": -1,
                        "occurrences": count,
                        "confidence": self._confidence(count),
                    }
                )

        habits.sort(key=lambda h: h["occurrences"], reverse=True)
        return habits

    @staticmethod
    def _confidence(occurrences: int) -> float:
        """Simple diminishing-returns curve, capped at 0.95 - more
        occurrences always help but never reach false certainty."""
        return round(min(0.95, 0.3 + occurrences * 0.08), 2)

    def habit_confidence(self, action: str) -> float:
        habits = [h for h in self.detected_habits(min_occurrences=1) if h["action"] == action]
        return max((h["confidence"] for h in habits), default=0.0)

    # -- deletion primitive - forget.py is the only intended caller -----
    def _delete_action(self, action: str) -> int:
        if not self._db_ok:
            before = len(self._fallback)
            self._fallback = [r for r in self._fallback if r["action"] != action]
            return before - len(self._fallback)
        cur = self._conn.cursor()
        cur.execute("DELETE FROM actions WHERE action=?", (action,))
        self._conn.commit()
        return cur.rowcount


_habit_memory: Optional[HabitMemory] = None


def get_habit_memory() -> HabitMemory:
    global _habit_memory
    if _habit_memory is None:
        _habit_memory = HabitMemory()
    return _habit_memory
