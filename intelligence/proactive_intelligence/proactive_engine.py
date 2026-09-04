"""
Proactive Engine (Phase 20.1 - Proactive Intelligence)
==================================================
Single entry point for the proactive_intelligence/ package: takes a
raw signal from anywhere else in ULTRON and drives it through the
full pipeline -

    event_detector.py        - is this actually a new, recognized event
    urgency_calculator.py    - how urgent is it
    user_disruption_guard.py - is now an acceptable moment to surface it
    suggestion_generator.py  - what should ULTRON actually say
    conversation_initiator.py - how should it be delivered (interrupt /
                                 next pause / silent / deferred)
    notification_manager.py  - persist it either way, so it's never lost

Mirrors conversation_engine.py's role in Phase 20 (a thin orchestrator
over otherwise-independent sub-modules that still work fine called
directly) and, like it, is the entry point every caller should reach
for by default - process_signal() is the one call a signal source
(system monitor, calendar poller, ULTRON_SHIELD alert, habit tracker,
anything else) needs to make.

process_signal() always enqueues a notification once an event clears
event_detector.py, regardless of the guard's decision - suppress/defer
still leave a durable record via notification_manager.py, they just
don't get delivered yet. Only conversation_initiator.py's mode
decides whether anything is actually said out loud right now
(MODE_INTERRUPT), and only that mode causes this module to mark the
notification delivered on the caller's behalf.

Storage: database/proactive_intelligence.db, table proactive_events
(this module's own table, logging the full pipeline outcome per
signal; user_disruption_guard.py/notification_manager.py/
conversation_initiator.py each keep their own tables in the same
database file).

Purely additive - nothing in Phase 1-20 imports from here except
conversation_initiator.py's read-only use of Phase 20's turn_manager.py.
"""

import json
import sqlite3
import threading
import time
from pathlib import Path
from typing import Dict, List, Optional

from core.logger import get_logger
from intelligence.proactive_intelligence.event_detector import get_event_detector
from intelligence.proactive_intelligence.urgency_calculator import get_urgency_calculator
from intelligence.proactive_intelligence.user_disruption_guard import get_user_disruption_guard
from intelligence.proactive_intelligence.suggestion_generator import get_suggestion_generator
from intelligence.proactive_intelligence.conversation_initiator import (
    get_conversation_initiator,
    MODE_INTERRUPT,
)
from intelligence.proactive_intelligence.notification_manager import get_notification_manager
from intelligence.conversation_layer.turn_manager import get_turn_manager

logger = get_logger("ultron.proactive_engine")

DB_PATH = Path(__file__).resolve().parent.parent.parent / "database" / "proactive_intelligence.db"

_instance: Optional["ProactiveEngine"] = None
_instance_lock = threading.Lock()


class ProactiveEngine:
    """Orchestrates event_detector / urgency_calculator /
    user_disruption_guard / suggestion_generator / conversation_initiator /
    notification_manager into the handful of calls a caller needs to
    turn a raw signal into (maybe) something said to the user."""

    def __init__(self, db_path: Path = DB_PATH):
        self._db_path = db_path
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
        self._conn.execute("""CREATE TABLE IF NOT EXISTS proactive_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT,
                event_type TEXT,
                category TEXT,
                urgency_level TEXT,
                urgency_score REAL,
                guard_decision TEXT,
                mode TEXT,
                notification_id INTEGER,
                details_json TEXT,
                timestamp REAL
            )""")
        self._conn.commit()

        self._detector = get_event_detector()
        self._urgency = get_urgency_calculator()
        self._guard = get_user_disruption_guard()
        self._suggestions = get_suggestion_generator()
        self._initiator = get_conversation_initiator()
        self._notifications = get_notification_manager()
        self._turns = get_turn_manager()

    def process_signal(
        self, raw_signal: Dict, context: Optional[Dict] = None, session_id: Optional[str] = None
    ) -> Dict:
        """The one call a signal source needs to make. Returns
        has_event=False with reasons if event_detector.py filtered the
        signal out (unrecognized or a duplicate); otherwise returns the
        full pipeline outcome."""
        detection = self._detector.detect(raw_signal)
        if not detection["is_event"]:
            return {"has_event": False, "reasons": detection["reasons"]}

        event = detection["event"]
        urgency = self._urgency.calculate(event, context)
        guard_decision = self._guard.evaluate(event, urgency["urgency_level"], context)
        suggestion = self._suggestions.generate(event, urgency["urgency_level"])
        initiation = self._initiator.decide(
            event, urgency["urgency_level"], guard_decision, suggestion["message"], session_id
        )
        notification = self._notifications.enqueue(
            event, urgency["urgency_level"], suggestion["message"], payload=event.get("payload")
        )

        if initiation["mode"] == MODE_INTERRUPT:
            notification = self._notifications.mark_delivered(notification["id"])
            logger.info(f"proactive interrupt on session {session_id}: {suggestion['message']}")

        self._log_event(session_id, event, urgency, guard_decision, initiation, notification["id"])

        return {
            "has_event": True,
            "event": event,
            "urgency": urgency,
            "guard_decision": guard_decision,
            "suggestion": suggestion,
            "initiation": initiation,
            "notification": notification,
        }

    def get_pending_notifications(self, limit: int = 20) -> List[Dict]:
        return self._notifications.get_pending(limit=limit)

    def get_next_deliverable(self, session_id: str) -> Optional[Dict]:
        """Convenience for a caller that owns the actual speaking/UI
        layer: the highest-priority pending notification, but only if
        the conversation currently has no active turn (checked directly
        against turn_manager.py, same source conversation_initiator.py
        itself reads) - so a caller polling this in a loop never gets
        told to speak while either side is already mid-turn. Does not
        mark it delivered - the caller does that via
        mark_notification_delivered() once it's actually shown."""
        if self._turns.get_current_turn(session_id) is not None:
            return None
        pending = self._notifications.get_pending(limit=1)
        return pending[0] if pending else None

    def mark_notification_delivered(self, notification_id: int) -> Optional[Dict]:
        return self._notifications.mark_delivered(notification_id)

    def dismiss_notification(self, notification_id: int) -> Optional[Dict]:
        return self._notifications.dismiss(notification_id)

    def snooze_notification(self, notification_id: int, minutes: float) -> Optional[Dict]:
        return self._notifications.snooze(notification_id, minutes)

    def set_do_not_disturb(self, enabled: bool, minutes: Optional[float] = None) -> Dict:
        return self._guard.set_dnd(enabled, minutes=minutes)

    def set_quiet_hours(self, start_hour: int, start_minute: int, end_hour: int, end_minute: int) -> Dict:
        return self._guard.set_quiet_hours(start_hour, start_minute, end_hour, end_minute)

    def get_recent_events(self, session_id: Optional[str] = None, limit: int = 20) -> List[Dict]:
        with self._lock:
            if session_id:
                rows = self._conn.execute(
                    """SELECT id, session_id, event_type, category, urgency_level, urgency_score,
                              guard_decision, mode, notification_id, details_json, timestamp
                       FROM proactive_events WHERE session_id = ? ORDER BY id DESC LIMIT ?""",
                    (session_id, limit),
                ).fetchall()
            else:
                rows = self._conn.execute(
                    """SELECT id, session_id, event_type, category, urgency_level, urgency_score,
                              guard_decision, mode, notification_id, details_json, timestamp
                       FROM proactive_events ORDER BY id DESC LIMIT ?""",
                    (limit,),
                ).fetchall()
        events = []
        for row in rows:
            (
                id_,
                sid,
                event_type,
                category,
                urgency_level,
                urgency_score,
                guard_decision,
                mode,
                notification_id,
                details_json,
                timestamp,
            ) = row
            try:
                details = json.loads(details_json) if details_json else {}
            except Exception:
                details = {}
            events.append(
                {
                    "id": id_,
                    "session_id": sid,
                    "event_type": event_type,
                    "category": category,
                    "urgency_level": urgency_level,
                    "urgency_score": urgency_score,
                    "guard_decision": guard_decision,
                    "mode": mode,
                    "notification_id": notification_id,
                    "details": details,
                    "timestamp": timestamp,
                }
            )
        return events

    def _log_event(
        self,
        session_id: Optional[str],
        event: Dict,
        urgency: Dict,
        guard_decision: Dict,
        initiation: Dict,
        notification_id: int,
    ) -> None:
        now = time.time()
        details = {
            "title": event.get("title"),
            "urgency_reasons": urgency.get("reasons"),
            "guard_reasons": guard_decision.get("reasons"),
            "initiation_reason": initiation.get("reason"),
        }
        with self._lock:
            self._conn.execute(
                """INSERT INTO proactive_events
                   (session_id, event_type, category, urgency_level, urgency_score,
                    guard_decision, mode, notification_id, details_json, timestamp)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    session_id,
                    event.get("event_type"),
                    event.get("category"),
                    urgency["urgency_level"],
                    urgency["urgency_score"],
                    guard_decision["decision"],
                    initiation["mode"],
                    notification_id,
                    json.dumps(details),
                    now,
                ),
            )
            self._conn.commit()


def get_proactive_engine() -> ProactiveEngine:
    """Process-wide ProactiveEngine singleton."""
    global _instance
    if _instance is None:
        with _instance_lock:
            if _instance is None:
                _instance = ProactiveEngine()
    return _instance
