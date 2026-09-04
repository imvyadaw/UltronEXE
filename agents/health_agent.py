"""
Health agent
============
Lightweight personal wellness tracker - water, sleep, exercise, and
screen-break reminders. Entirely local (SQLite), no wearable/health-API
integration, so it works offline like the rest of Ultron. Pair with
core/scheduler.py to nudge "time for a break" / "log your water" on an
interval.
"""

import sqlite3
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict

from agents.base_agent import BaseAgent

DB_PATH = Path(__file__).resolve().parent.parent / "storage" / "sqlite" / "health.db"

# A conservative default; not medical advice - just a nudging target.
DAILY_WATER_GOAL_ML = 2000


class HealthAgent(BaseAgent):
    """Log and summarize simple wellness metrics."""

    capabilities = ["health", "wellness", "water", "sleep", "exercise"]

    def __init__(self):
        super().__init__("health", "Local wellness tracker - water/sleep/exercise/break logging")
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
        self._conn.execute("""CREATE TABLE IF NOT EXISTS logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                kind TEXT,
                value REAL,
                note TEXT,
                logged_at REAL
            )""")
        self._conn.commit()
        self._last_break_reminder = time.time()

    def _log(self, kind: str, value: float, note: str = "") -> Dict:
        try:
            self._conn.execute(
                "INSERT INTO logs (kind, value, note, logged_at) VALUES (?, ?, ?, ?)",
                (kind, value, note, time.time()),
            )
            self._conn.commit()
            return {"success": True, "kind": kind, "value": value}
        except Exception as e:
            return {"error": str(e)}

    def log_water(self, ml: float) -> Dict:
        """Log water intake in millilitres."""
        return self._log("water", ml)

    def log_sleep(self, hours: float, note: str = "") -> Dict:
        """Log hours of sleep for the previous night."""
        return self._log("sleep", hours, note)

    def log_exercise(self, minutes: float, note: str = "") -> Dict:
        """Log minutes of exercise/activity."""
        return self._log("exercise", minutes, note)

    def log_mood_score(self, score: float, note: str = "") -> Dict:
        """Log a quick 1-10 wellbeing self-rating. For anything richer,
        see memory/emotional_memory.py."""
        return self._log("mood", score, note)

    def _today_total(self, kind: str) -> float:
        start_of_day = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
        cur = self._conn.cursor()
        cur.execute("SELECT COALESCE(SUM(value), 0) FROM logs WHERE kind = ? AND logged_at >= ?", (kind, start_of_day))
        return cur.fetchone()[0]

    def daily_summary(self) -> Dict:
        """Totals for today across all tracked metrics."""
        water = self._today_total("water")
        exercise = self._today_total("exercise")
        cur = self._conn.cursor()
        start_of_day = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
        cur.execute(
            "SELECT value FROM logs WHERE kind = 'sleep' AND logged_at >= ? ORDER BY logged_at DESC LIMIT 1",
            (start_of_day,),
        )
        row = cur.fetchone()
        sleep = row[0] if row else None
        return {
            "water_ml": water,
            "water_goal_ml": DAILY_WATER_GOAL_ML,
            "water_goal_met": water >= DAILY_WATER_GOAL_ML,
            "exercise_minutes": exercise,
            "sleep_hours_last_logged": sleep,
        }

    def history(self, kind: str, days: int = 7) -> Dict:
        """Raw log entries for a metric over the last `days` days."""
        cutoff = (datetime.now() - timedelta(days=days)).timestamp()
        cur = self._conn.cursor()
        cur.execute(
            "SELECT value, note, logged_at FROM logs WHERE kind = ? AND logged_at >= ? ORDER BY logged_at",
            (kind, cutoff),
        )
        rows = cur.fetchall()
        entries = [{"value": r[0], "note": r[1], "logged_at": r[2]} for r in rows]
        return {"kind": kind, "days": days, "entries": entries}

    def should_take_a_break(self, interval_minutes: int = 45) -> Dict:
        """True if `interval_minutes` have passed since the last break
        reminder - call periodically from a scheduler loop."""
        elapsed = (time.time() - self._last_break_reminder) / 60
        due = elapsed >= interval_minutes
        if due:
            self._last_break_reminder = time.time()
        return {"due": due, "minutes_since_last_reminder": round(elapsed, 1)}
