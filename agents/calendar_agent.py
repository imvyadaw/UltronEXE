"""
Calendar agent
==============
Local, offline calendar - no Google/Outlook OAuth required. Events are
stored in SQLite under storage/sqlite/, same pattern as
memory/long_term/long_term.py. core/scheduler.py can poll
upcoming_events() to fire reminders; voice/text just calls this
directly for "what's on my calendar" / "schedule a meeting" requests.
"""

import sqlite3
import time
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict

from agents.base_agent import BaseAgent

DB_PATH = Path(__file__).resolve().parent.parent / "storage" / "sqlite" / "calendar.db"


class CalendarAgent(BaseAgent):
    """Create, list, and remove local calendar events."""

    capabilities = ["calendar", "events", "schedule", "reminders"]

    def __init__(self):
        super().__init__("calendar", "Local offline calendar (SQLite) - create/list/remove events")
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
        self._conn.execute("""CREATE TABLE IF NOT EXISTS events (
                id TEXT PRIMARY KEY,
                title TEXT,
                start_time TEXT,
                end_time TEXT,
                location TEXT,
                notes TEXT,
                created_at REAL
            )""")
        self._conn.commit()

    def add_event(self, title: str, start_time: str, end_time: str = None, location: str = "", notes: str = "") -> Dict:
        """Add an event. `start_time`/`end_time` are ISO-8601 strings
        (e.g. '2026-08-05T14:00:00')."""
        try:
            datetime.fromisoformat(start_time)
            if end_time:
                datetime.fromisoformat(end_time)
        except ValueError as e:
            return {"error": f"Invalid datetime: {e}"}

        try:
            event_id = str(uuid.uuid4())[:8]
            self._conn.execute(
                "INSERT INTO events (id, title, start_time, end_time, location, notes, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (event_id, title, start_time, end_time, location, notes, time.time()),
            )
            self._conn.commit()
            return {"success": True, "id": event_id, "title": title, "start_time": start_time}
        except Exception as e:
            return {"error": str(e)}

    def list_events(self, start_time: str = None, end_time: str = None) -> Dict:
        """List events, optionally filtered to an ISO-8601 time range."""
        try:
            cur = self._conn.cursor()
            if start_time and end_time:
                cur.execute(
                    "SELECT id, title, start_time, end_time, location, notes FROM events "
                    "WHERE start_time >= ? AND start_time <= ? ORDER BY start_time",
                    (start_time, end_time),
                )
            else:
                cur.execute("SELECT id, title, start_time, end_time, location, notes FROM events ORDER BY start_time")
            rows = cur.fetchall()
            events = [
                {"id": r[0], "title": r[1], "start_time": r[2], "end_time": r[3], "location": r[4], "notes": r[5]}
                for r in rows
            ]
            return {"count": len(events), "events": events}
        except Exception as e:
            return {"error": str(e)}

    def upcoming_events(self, within_hours: int = 24) -> Dict:
        """Events starting between now and `within_hours` from now - what
        core/scheduler.py polls to fire reminders."""
        now = datetime.now()
        window_end = now + timedelta(hours=within_hours)
        return self.list_events(now.isoformat(), window_end.isoformat())

    def delete_event(self, event_id: str) -> Dict:
        """Delete an event by id."""
        try:
            cur = self._conn.cursor()
            cur.execute("DELETE FROM events WHERE id = ?", (event_id,))
            self._conn.commit()
            if cur.rowcount == 0:
                return {"error": f"No event found with id {event_id}"}
            return {"success": True, "deleted_id": event_id}
        except Exception as e:
            return {"error": str(e)}

    def update_event(self, event_id: str, **fields) -> Dict:
        """Update one or more fields (title, start_time, end_time, location, notes) of an event."""
        allowed = {"title", "start_time", "end_time", "location", "notes"}
        updates = {k: v for k, v in fields.items() if k in allowed and v is not None}
        if not updates:
            return {"error": "No valid fields to update"}
        try:
            set_clause = ", ".join(f"{k} = ?" for k in updates)
            cur = self._conn.cursor()
            cur.execute(f"UPDATE events SET {set_clause} WHERE id = ?", (*updates.values(), event_id))
            self._conn.commit()
            if cur.rowcount == 0:
                return {"error": f"No event found with id {event_id}"}
            return {"success": True, "id": event_id, "updated": list(updates.keys())}
        except Exception as e:
            return {"error": str(e)}
