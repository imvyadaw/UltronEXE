"""Episodic memory
================
Records specific, timestamped things that *happened* ("user asked me
to close Chrome at 3pm", "deployment failed at 9:12am") - distinct
from memory/semantic_memory.py's general facts/concepts and
memory/long_term/long_term.py's durable key/value user facts. This is
the "diary" layer: a chronological log of events with optional context,
useful for "what did we do earlier today" style questions and for
memory/emotional_memory.py to attach mood to a specific event.
"""

import sqlite3
import time
from datetime import datetime
from pathlib import Path
from typing import Dict

DB_PATH = Path(__file__).resolve().parent.parent / "storage" / "sqlite" / "episodic_memory.db"


class EpisodicMemory:
    """Chronological log of discrete events/experiences."""

    def __init__(self):
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
        self._conn.execute("""CREATE TABLE IF NOT EXISTS episodes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event TEXT,
                context TEXT,
                tags TEXT,
                occurred_at REAL
            )""")
        self._conn.commit()

    def record_event(self, event: str, context: str = "", tags: str = "") -> Dict:
        """Log a single event as it happens. `tags` is a free-text,
        comma-separated string for later filtering."""
        try:
            self._conn.execute(
                "INSERT INTO episodes (event, context, tags, occurred_at) VALUES (?, ?, ?, ?)",
                (event, context, tags, time.time()),
            )
            self._conn.commit()
            return {"success": True, "event": event}
        except Exception as e:
            return {"error": str(e)}

    def recent_events(self, limit: int = 20) -> Dict:
        """Most recent events, newest first."""
        try:
            cur = self._conn.cursor()
            cur.execute(
                "SELECT id, event, context, tags, occurred_at FROM episodes ORDER BY occurred_at DESC LIMIT ?", (limit,)
            )
            rows = cur.fetchall()
            events = [{"id": r[0], "event": r[1], "context": r[2], "tags": r[3], "occurred_at": r[4]} for r in rows]
            return {"count": len(events), "events": events}
        except Exception as e:
            return {"error": str(e)}

    def events_today(self) -> Dict:
        """All events logged since local midnight."""
        start_of_day = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
        return self.events_between(start_of_day, time.time())

    def events_between(self, start_ts: float, end_ts: float) -> Dict:
        """All events between two unix timestamps."""
        try:
            cur = self._conn.cursor()
            cur.execute(
                "SELECT id, event, context, tags, occurred_at FROM episodes WHERE occurred_at BETWEEN ? AND ? ORDER BY occurred_at",
                (start_ts, end_ts),
            )
            rows = cur.fetchall()
            events = [{"id": r[0], "event": r[1], "context": r[2], "tags": r[3], "occurred_at": r[4]} for r in rows]
            return {"count": len(events), "events": events}
        except Exception as e:
            return {"error": str(e)}

    def search_events(self, query: str, limit: int = 20) -> Dict:
        """Simple substring search over event text/context/tags."""
        try:
            like = f"%{query}%"
            cur = self._conn.cursor()
            cur.execute(
                "SELECT id, event, context, tags, occurred_at FROM episodes "
                "WHERE event LIKE ? OR context LIKE ? OR tags LIKE ? ORDER BY occurred_at DESC LIMIT ?",
                (like, like, like, limit),
            )
            rows = cur.fetchall()
            events = [{"id": r[0], "event": r[1], "context": r[2], "tags": r[3], "occurred_at": r[4]} for r in rows]
            return {"query": query, "count": len(events), "events": events}
        except Exception as e:
            return {"error": str(e)}
