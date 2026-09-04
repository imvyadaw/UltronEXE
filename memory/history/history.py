"""Conversation history store
===========================
Persists full conversation sessions to SQLite so history survives a
restart. Today's live session still lives in-memory on
ai.cloud_models.groq_client.UltronGroqClient.conversation_history - this
module is for saving/loading full past sessions on top of that.
"""

import json
import sqlite3
import time
from pathlib import Path
from typing import Dict, List

DB_PATH = Path(__file__).resolve().parents[2] / "storage" / "sqlite" / "history.db"


class ConversationHistoryStore:
    """Persist full conversation sessions to disk."""

    def __init__(self):
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
        self._conn.execute("""CREATE TABLE IF NOT EXISTS sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                started_at REAL,
                ended_at REAL,
                messages TEXT
            )""")
        self._conn.commit()

    def save_session(self, messages: List[Dict], started_at: float = None) -> Dict:
        """Save a full conversation session (list of {"role", "content"} dicts)."""
        try:
            cur = self._conn.cursor()
            cur.execute(
                "INSERT INTO sessions (started_at, ended_at, messages) VALUES (?, ?, ?)",
                (started_at or time.time(), time.time(), json.dumps(messages)),
            )
            self._conn.commit()
            return {"success": True, "session_id": cur.lastrowid, "message_count": len(messages)}
        except Exception as e:
            return {"error": str(e)}

    def load_session(self, session_id: int) -> Dict:
        """Load a saved session by id."""
        try:
            cur = self._conn.cursor()
            cur.execute("SELECT started_at, ended_at, messages FROM sessions WHERE id = ?", (session_id,))
            row = cur.fetchone()
            if not row:
                return {"error": f"No session with id {session_id}"}
            return {
                "session_id": session_id,
                "started_at": row[0],
                "ended_at": row[1],
                "messages": json.loads(row[2]),
            }
        except Exception as e:
            return {"error": str(e)}

    def list_sessions(self, limit: int = 20) -> Dict:
        """List recent sessions (most recent first), without full message bodies."""
        try:
            cur = self._conn.cursor()
            cur.execute(
                "SELECT id, started_at, ended_at, messages FROM sessions ORDER BY id DESC LIMIT ?",
                (limit,),
            )
            rows = cur.fetchall()
            sessions = []
            for row in rows:
                msgs = json.loads(row[3])
                preview = msgs[0]["content"][:80] if msgs else ""
                sessions.append(
                    {
                        "session_id": row[0],
                        "started_at": row[1],
                        "ended_at": row[2],
                        "message_count": len(msgs),
                        "preview": preview,
                    }
                )
            return {"sessions": sessions, "count": len(sessions)}
        except Exception as e:
            return {"error": str(e)}

    def delete_session(self, session_id: int) -> Dict:
        """Delete a saved session."""
        try:
            cur = self._conn.cursor()
            cur.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
            self._conn.commit()
            return {"success": True, "deleted_id": session_id, "rows_affected": cur.rowcount}
        except Exception as e:
            return {"error": str(e)}
