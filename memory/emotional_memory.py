"""Emotional memory
=================
Tracks the user's mood/sentiment over time and can attach an emotional
tag to a specific memory (an episodic event, a note, etc.) so Ultron
can be sensitive to how someone felt about something, not just what
happened. Kept as its own store rather than a column bolted onto
episodic memory, since not every event has - or needs - an emotional
tag, and mood is also logged on its own (agents/health_agent.py's
1-10 self-rating is separate and lighter-weight; this module is for
richer labeled sentiment + trend analysis).
"""

import sqlite3
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Optional

DB_PATH = Path(__file__).resolve().parent.parent / "storage" / "sqlite" / "emotional_memory.db"

# Simple valence map for trend scoring; unrecognized labels score 0 (neutral).
_VALENCE = {
    "joy": 2,
    "excited": 2,
    "happy": 2,
    "grateful": 2,
    "proud": 2,
    "calm": 1,
    "content": 1,
    "neutral": 0,
    "tired": -1,
    "bored": -1,
    "anxious": -2,
    "stressed": -2,
    "frustrated": -2,
    "sad": -2,
    "angry": -3,
    "overwhelmed": -3,
}


class EmotionalMemory:
    """Log mood entries and attach emotional tags to other memories."""

    def __init__(self):
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
        self._conn.execute("""CREATE TABLE IF NOT EXISTS moods (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                emotion TEXT,
                intensity INTEGER,
                note TEXT,
                related_memory_id TEXT,
                logged_at REAL
            )""")
        self._conn.commit()

    def log_mood(
        self, emotion: str, intensity: int = 3, note: str = "", related_memory_id: Optional[str] = None
    ) -> Dict:
        """Log an emotion label (e.g. 'anxious', 'excited') with a 1-5
        intensity, optionally linked to another memory's id (e.g. an
        episodic_memory.py event id)."""
        try:
            self._conn.execute(
                "INSERT INTO moods (emotion, intensity, note, related_memory_id, logged_at) VALUES (?, ?, ?, ?, ?)",
                (emotion.lower(), intensity, note, related_memory_id, time.time()),
            )
            self._conn.commit()
            return {"success": True, "emotion": emotion, "intensity": intensity}
        except Exception as e:
            return {"error": str(e)}

    def get_recent_mood(self, limit: int = 10) -> Dict:
        """Most recent mood entries, newest first."""
        try:
            cur = self._conn.cursor()
            cur.execute(
                "SELECT emotion, intensity, note, related_memory_id, logged_at FROM moods ORDER BY logged_at DESC LIMIT ?",
                (limit,),
            )
            rows = cur.fetchall()
            entries = [
                {"emotion": r[0], "intensity": r[1], "note": r[2], "related_memory_id": r[3], "logged_at": r[4]}
                for r in rows
            ]
            return {"count": len(entries), "entries": entries}
        except Exception as e:
            return {"error": str(e)}

    def mood_trend(self, days: int = 7) -> Dict:
        """Average valence score over the last `days` days, plus a rough
        label (improving/declining/steady) comparing the first vs second
        half of the window. Not a clinical measure - just a lightweight
        signal for Ultron to notice a rough patch."""
        cutoff = (datetime.now() - timedelta(days=days)).timestamp()
        try:
            cur = self._conn.cursor()
            cur.execute(
                "SELECT emotion, intensity, logged_at FROM moods WHERE logged_at >= ? ORDER BY logged_at", (cutoff,)
            )
            rows = cur.fetchall()
            if not rows:
                return {"days": days, "entries": 0, "average_valence": 0, "trend": "no data"}

            scored = [(_VALENCE.get(emotion, 0) * (intensity / 3), ts) for emotion, intensity, ts in rows]
            avg = sum(s for s, _ in scored) / len(scored)

            mid = len(scored) // 2
            first_half = scored[:mid] or scored
            second_half = scored[mid:] or scored
            first_avg = sum(s for s, _ in first_half) / len(first_half)
            second_avg = sum(s for s, _ in second_half) / len(second_half)

            if second_avg - first_avg > 0.5:
                trend = "improving"
            elif first_avg - second_avg > 0.5:
                trend = "declining"
            else:
                trend = "steady"

            return {"days": days, "entries": len(rows), "average_valence": round(avg, 2), "trend": trend}
        except Exception as e:
            return {"error": str(e)}

    def tag_memory(self, related_memory_id: str, emotion: str, intensity: int = 3, note: str = "") -> Dict:
        """Convenience wrapper: attach an emotion to an existing memory
        (e.g. an episodic_memory.py event id) by id."""
        return self.log_mood(emotion, intensity, note, related_memory_id)
