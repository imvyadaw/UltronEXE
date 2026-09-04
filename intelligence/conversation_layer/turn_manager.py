"""
Turn Manager (Phase 20 - Conversation Layer)
==================================================
Source of truth for who's currently speaking in a conversation
session and the full turn-by-turn history behind it. Every other
module in this package reads from here rather than keeping its own
notion of "whose turn is it" - continuity_tracker.py diffs consecutive
turns' text, barge_in_detector.py needs to know if the assistant turn
it's being asked about is actually still in_progress, and
conversation_engine.py drives the whole start/end/interrupt lifecycle
through this module.

A session can have at most one in_progress turn at a time. Starting a
new turn implicitly closes any dangling in_progress turn for that
session as completed - callers that want to record an interruption
instead of a clean close should call interrupt_turn() first (this is
exactly what conversation_engine.py does when barge_in_detector.py
reports a barge-in: interrupt the assistant's turn, then start the
user's).

Storage: database/conversation_history.db, table turns. Also keeps an
in-memory {session_id: turn_id} map of current turns so
get_current_turn() doesn't need a query for the hot path.
"""

import sqlite3
import threading
import time
from pathlib import Path
from typing import Dict, List, Optional

DB_PATH = Path(__file__).resolve().parent.parent.parent / "database" / "conversation_history.db"

_instance: Optional["TurnManager"] = None
_instance_lock = threading.Lock()

SPEAKER_USER = "user"
SPEAKER_ASSISTANT = "assistant"

STATUS_IN_PROGRESS = "in_progress"
STATUS_COMPLETED = "completed"
STATUS_INTERRUPTED = "interrupted"

TURN_TYPE_SPEECH = "speech"
TURN_TYPE_TEXT = "text"


class TurnManager:
    """Owns turn lifecycle (start/end/interrupt) and history for
    every conversation session."""

    def __init__(self, db_path: Path = DB_PATH):
        self._db_path = db_path
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
        self._conn.execute("""CREATE TABLE IF NOT EXISTS turns (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT,
                turn_number INTEGER,
                speaker TEXT,
                turn_type TEXT,
                text TEXT,
                status TEXT,
                started_at REAL,
                ended_at REAL,
                duration REAL
            )""")
        self._conn.commit()
        # session_id -> in-progress turn id, so get_current_turn() and
        # the barge-in hot path don't need a query every call
        self._current_turn_id: Dict[str, int] = {}

    def start_turn(self, session_id: str, speaker: str, turn_type: str = TURN_TYPE_SPEECH) -> Dict:
        """Closes any dangling in_progress turn for this session as
        completed, then opens a new one and returns it."""
        with self._lock:
            dangling_id = self._current_turn_id.get(session_id)
            if dangling_id is not None:
                self._close_turn_locked(dangling_id, status=STATUS_COMPLETED)

            turn_number = self._next_turn_number_locked(session_id)
            now = time.time()
            cur = self._conn.execute(
                """INSERT INTO turns (session_id, turn_number, speaker, turn_type, text, status,
                                       started_at, ended_at, duration)
                   VALUES (?, ?, ?, ?, NULL, ?, ?, NULL, NULL)""",
                (session_id, turn_number, speaker, turn_type, STATUS_IN_PROGRESS, now),
            )
            self._conn.commit()
            turn_id = cur.lastrowid
            self._current_turn_id[session_id] = turn_id
        return self.get_turn(turn_id)

    def end_turn(self, turn_id: int, text: Optional[str] = None, status: str = STATUS_COMPLETED) -> Optional[Dict]:
        with self._lock:
            self._close_turn_locked(turn_id, status=status, text=text)
        return self.get_turn(turn_id)

    def interrupt_turn(self, turn_id: int, text: Optional[str] = None) -> Optional[Dict]:
        """Mark a turn cut off mid-way - what conversation_engine.py
        calls on the assistant's turn when barge_in_detector.py
        reports the user talked over it."""
        return self.end_turn(turn_id, text=text, status=STATUS_INTERRUPTED)

    def get_current_turn(self, session_id: str) -> Optional[Dict]:
        turn_id = self._current_turn_id.get(session_id)
        if turn_id is None:
            return None
        turn = self.get_turn(turn_id)
        # in-memory map can go stale if a turn was closed by id directly
        # rather than through start_turn()'s dangling-close path
        if turn and turn["status"] != STATUS_IN_PROGRESS:
            self._current_turn_id.pop(session_id, None)
            return None
        return turn

    def get_turn(self, turn_id: int) -> Optional[Dict]:
        with self._lock:
            row = self._conn.execute(
                """SELECT id, session_id, turn_number, speaker, turn_type, text, status,
                          started_at, ended_at, duration FROM turns WHERE id = ?""",
                (turn_id,),
            ).fetchone()
        return self._row_to_turn(row) if row else None

    def get_history(self, session_id: str, limit: int = 20) -> List[Dict]:
        with self._lock:
            rows = self._conn.execute(
                """SELECT id, session_id, turn_number, speaker, turn_type, text, status,
                          started_at, ended_at, duration
                   FROM turns WHERE session_id = ? ORDER BY turn_number DESC LIMIT ?""",
                (session_id, limit),
            ).fetchall()
        return [self._row_to_turn(r) for r in reversed(rows)]

    def get_last_n_turns(self, session_id: str, n: int = 2) -> List[Dict]:
        """Convenience for continuity_tracker.py, which typically only
        needs the immediately preceding turn(s)."""
        return self.get_history(session_id, limit=n)

    def _next_turn_number_locked(self, session_id: str) -> int:
        row = self._conn.execute("SELECT MAX(turn_number) FROM turns WHERE session_id = ?", (session_id,)).fetchone()
        return (row[0] or 0) + 1

    def _close_turn_locked(self, turn_id: int, status: str, text: Optional[str] = None) -> None:
        now = time.time()
        row = self._conn.execute("SELECT started_at, session_id FROM turns WHERE id = ?", (turn_id,)).fetchone()
        if row is None:
            return
        started_at, session_id = row
        duration = max(0.0, now - started_at) if started_at else None
        if text is not None:
            self._conn.execute(
                "UPDATE turns SET status = ?, ended_at = ?, duration = ?, text = ? WHERE id = ?",
                (status, now, duration, text, turn_id),
            )
        else:
            self._conn.execute(
                "UPDATE turns SET status = ?, ended_at = ?, duration = ? WHERE id = ?",
                (status, now, duration, turn_id),
            )
        self._conn.commit()
        if self._current_turn_id.get(session_id) == turn_id:
            self._current_turn_id.pop(session_id, None)

    @staticmethod
    def _row_to_turn(row) -> Dict:
        id_, session_id, turn_number, speaker, turn_type, text, status, started_at, ended_at, duration = row
        return {
            "turn_id": id_,
            "session_id": session_id,
            "turn_number": turn_number,
            "speaker": speaker,
            "turn_type": turn_type,
            "text": text,
            "status": status,
            "started_at": started_at,
            "ended_at": ended_at,
            "duration": duration,
        }


def get_turn_manager() -> TurnManager:
    """Process-wide TurnManager singleton."""
    global _instance
    if _instance is None:
        with _instance_lock:
            if _instance is None:
                _instance = TurnManager()
    return _instance
