"""
Conversation Initiator (Phase 20.1 - Proactive Intelligence)
==================================================
Given that user_disruption_guard.py has already said it's okay to
surface something, decides *how* to actually bring it up: cut in on
the current conversation right now, wait for the next natural
opening, or just leave it as a silent notification without ever
speaking it. This is the one module in this package that reaches into
Phase 20's conversation_layer/ (turn_manager.py specifically) to check
whether the assistant or the user currently has the floor - a
critical alert can justify interrupting, but a routine nudge should
never cut into the middle of either side actually talking.

Only a critical-urgency ALLOW ever produces mode "interrupt". A
non-critical ALLOW with no active turn, or with the assistant/user
mid-turn, becomes "next_pause" - queued for the next time
conversation_engine.py opens an assistant turn, rather than spoken
immediately. A DEFER from the guard becomes "deferred" (try again once
conditions change), and a SUPPRESS becomes "silent_notification" (goes
to notification_manager.py's queue only, never spoken).

Storage: database/proactive_intelligence.db, table initiations - a log
of every delivery-mode decision, mirroring conversation_engine.py's
own conversation_events table in Phase 20.

This is the one module here that imports from intelligence.conversation_layer
(turn_manager.py, read-only - it never starts/ends a turn itself,
that stays the caller's job once it actually delivers something).
"""

import sqlite3
import threading
import time
from pathlib import Path
from typing import Dict, Optional

from intelligence.conversation_layer.turn_manager import get_turn_manager, SPEAKER_ASSISTANT

DB_PATH = Path(__file__).resolve().parent.parent.parent / "database" / "proactive_intelligence.db"

_instance: Optional["ConversationInitiator"] = None
_instance_lock = threading.Lock()

URGENCY_CRITICAL = "critical"

DECISION_ALLOW = "allow"
DECISION_DEFER = "defer"
DECISION_SUPPRESS = "suppress"

MODE_INTERRUPT = "interrupt"
MODE_NEXT_PAUSE = "next_pause"
MODE_SILENT = "silent_notification"
MODE_DEFERRED = "deferred"


class ConversationInitiator:
    """(event, urgency_level, guard_decision, message, session_id) ->
    {"mode", "message", "reason"}."""

    def __init__(self, db_path: Path = DB_PATH):
        self._db_path = db_path
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
        self._conn.execute("""CREATE TABLE IF NOT EXISTS initiations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT,
                event_type TEXT,
                category TEXT,
                urgency_level TEXT,
                mode TEXT,
                message TEXT,
                timestamp REAL
            )""")
        self._conn.commit()
        self._turns = get_turn_manager()

    def decide(
        self, event: Dict, urgency_level: str, guard_decision: Dict, message: str, session_id: Optional[str] = None
    ) -> Dict:
        decision = guard_decision.get("decision")
        is_critical = urgency_level == URGENCY_CRITICAL

        if decision == DECISION_SUPPRESS:
            mode, reason = MODE_SILENT, "guard suppressed this - notification only, never spoken"
        elif decision == DECISION_DEFER:
            mode, reason = MODE_DEFERRED, guard_decision.get("reason", "guard deferred this")
        elif decision == DECISION_ALLOW:
            mode, reason = self._mode_for_allowed(is_critical, session_id)
        else:
            # unrecognized guard decision - fail closed to silent rather
            # than risk speaking something the guard didn't clear
            mode, reason = MODE_SILENT, f"unrecognized guard decision '{decision}' - defaulting to silent"

        self._log(session_id, event.get("event_type"), event.get("category"), urgency_level, mode, message)
        return {"mode": mode, "message": message, "reason": reason}

    def get_recent(self, session_id: Optional[str] = None, limit: int = 20) -> list:
        with self._lock:
            if session_id:
                rows = self._conn.execute(
                    """SELECT id, session_id, event_type, category, urgency_level, mode, message, timestamp
                       FROM initiations WHERE session_id = ? ORDER BY id DESC LIMIT ?""",
                    (session_id, limit),
                ).fetchall()
            else:
                rows = self._conn.execute(
                    """SELECT id, session_id, event_type, category, urgency_level, mode, message, timestamp
                       FROM initiations ORDER BY id DESC LIMIT ?""",
                    (limit,),
                ).fetchall()
        return [
            {
                "id": r[0],
                "session_id": r[1],
                "event_type": r[2],
                "category": r[3],
                "urgency_level": r[4],
                "mode": r[5],
                "message": r[6],
                "timestamp": r[7],
            }
            for r in rows
        ]

    def _mode_for_allowed(self, is_critical: bool, session_id: Optional[str]):
        if is_critical:
            return MODE_INTERRUPT, "urgency is critical - clear to interrupt now"

        if not session_id:
            return MODE_NEXT_PAUSE, "no session to check turn state against - queuing for next opening"

        current_turn = self._turns.get_current_turn(session_id)
        if current_turn is None:
            return MODE_NEXT_PAUSE, "no active turn right now - queuing for the next natural opening"
        if current_turn["speaker"] == SPEAKER_ASSISTANT:
            return MODE_NEXT_PAUSE, "assistant is mid-turn - waiting for it to finish rather than talking over itself"
        return MODE_NEXT_PAUSE, "user is mid-turn - not critical enough to talk over them"

    def _log(
        self,
        session_id: Optional[str],
        event_type: Optional[str],
        category: Optional[str],
        urgency_level: str,
        mode: str,
        message: str,
    ) -> None:
        now = time.time()
        with self._lock:
            self._conn.execute(
                """INSERT INTO initiations
                   (session_id, event_type, category, urgency_level, mode, message, timestamp)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (session_id, event_type, category, urgency_level, mode, message, now),
            )
            self._conn.commit()


def get_conversation_initiator() -> ConversationInitiator:
    """Process-wide ConversationInitiator singleton."""
    global _instance
    if _instance is None:
        with _instance_lock:
            if _instance is None:
                _instance = ConversationInitiator()
    return _instance
