"""
Conversation Engine (Phase 20 - Conversation Layer)
==================================================
Single entry point for the conversation_layer/ package: drives the
full turn-taking lifecycle for a session and ties together

    turn_manager.py       - who's speaking, turn history, start/end/interrupt
    barge_in_detector.py  - is incoming speech during the assistant's
                             turn a real interruption
    continuity_tracker.py - does this turn continue the last topic
    response_timer.py     - is a pause long enough to mean "respond now"
    emotional_tone.py     - what tone is the user in, what tone should
                             the assistant answer in
    filler_generator.py   - what to say if the real response will take
                             a moment

Mirrors decision_gate.py's role in Phase 19.8 (a thin orchestrator
over otherwise-independent sub-modules that still work fine called
directly) and takes the entry-point role itself for the same reason:
every exchange that needs turn-taking logic ends up here regardless
of which path led to it.

decide_on_speech() is read/compute-only against barge_in_detector.py
and continuity_tracker.py, and only writes through turn_manager.py's
own persistence - it never touches response_timer.py's adaptive
thresholds directly. Only report_response_outcome(), by handing off
to response_timer.py's record_outcome(), can move a threshold.

Storage: database/conversation_history.db, table conversation_events
(this module's own table, logging what was decided for each user
turn; turn_manager.py and response_timer.py each keep their own
tables in the same database file).

Purely additive - nothing in Phase 1-19.9 imports from here.
"""

import json
import sqlite3
import threading
import time
from pathlib import Path
from typing import Dict, List, Optional

from core.logger import get_logger
from intelligence.conversation_layer.turn_manager import (
    get_turn_manager,
    SPEAKER_USER,
    SPEAKER_ASSISTANT,
    TURN_TYPE_SPEECH,
)
from intelligence.conversation_layer.barge_in_detector import get_barge_in_detector
from intelligence.conversation_layer.continuity_tracker import get_continuity_tracker
from intelligence.conversation_layer.response_timer import get_response_timer, DECISION_RESPOND
from intelligence.conversation_layer.emotional_tone import get_emotional_tone
from intelligence.conversation_layer.filler_generator import get_filler_generator, REASON_THINKING

logger = get_logger("ultron.conversation_engine")

DB_PATH = Path(__file__).resolve().parent.parent.parent / "database" / "conversation_history.db"

_instance: Optional["ConversationEngine"] = None
_instance_lock = threading.Lock()

# a filler is only worth speaking if the real response is going to
# take noticeably longer than a natural reply gap
_FILLER_LATENCY_THRESHOLD_SECONDS = 1.5


class ConversationEngine:
    """Orchestrates turn_manager / barge_in_detector / continuity_tracker /
    response_timer / emotional_tone / filler_generator into the handful
    of calls a caller needs to run a session's turn-taking."""

    def __init__(self, db_path: Path = DB_PATH):
        self._db_path = db_path
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
        self._conn.execute("""CREATE TABLE IF NOT EXISTS conversation_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT,
                turn_id INTEGER,
                event_type TEXT,
                tone TEXT,
                is_continuation INTEGER,
                topic_shift_score REAL,
                barge_in_detected INTEGER,
                barge_in_type TEXT,
                filler_used TEXT,
                details_json TEXT,
                timestamp REAL
            )""")
        self._conn.commit()

        self._turns = get_turn_manager()
        self._barge_in = get_barge_in_detector()
        self._continuity = get_continuity_tracker()
        self._timer = get_response_timer()
        self._tone = get_emotional_tone()
        self._filler = get_filler_generator()

    def start_user_turn(self, session_id: str, turn_type: str = TURN_TYPE_SPEECH) -> Dict:
        return self._turns.start_turn(session_id, SPEAKER_USER, turn_type=turn_type)

    def handle_incoming_speech(self, session_id: str, incoming_signal: Dict) -> Dict:
        """Called whenever speech is detected while the assistant may
        be mid-turn. If it's a real barge-in, interrupts the
        assistant's turn and opens a new user turn; otherwise a no-op
        beyond logging the check."""
        current = self._turns.get_current_turn(session_id)
        assistant_is_speaking = bool(current and current["speaker"] == SPEAKER_ASSISTANT)
        assistant_started_at = current["started_at"] if assistant_is_speaking else None

        result = self._barge_in.detect(
            assistant_is_speaking=assistant_is_speaking,
            assistant_turn_started_at=assistant_started_at,
            incoming_signal=incoming_signal,
            now=time.time(),
        )

        new_turn = None
        if result["is_barge_in"]:
            self._turns.interrupt_turn(current["turn_id"])
            new_turn = self._turns.start_turn(session_id, SPEAKER_USER)
            logger.info(
                f"barge-in on session {session_id}: type={result['barge_in_type']} "
                f"confidence={result['confidence']:.2f}"
            )
            self._log_event(
                session_id,
                new_turn["turn_id"],
                "barge_in",
                barge_in_detected=True,
                barge_in_type=result["barge_in_type"],
                details={"confidence": result["confidence"], "reasons": result["reasons"]},
            )

        result["new_user_turn"] = new_turn
        return result

    def process_user_utterance(self, session_id: str, text: str, pause_duration: float) -> Dict:
        """Given the user's text-so-far and how long they've paused,
        combines endpointing, continuity, and tone into one decision
        bundle - whether to respond now, how the new text relates to
        the prior turn, and what tone to answer in."""
        timing = self._timer.should_respond(session_id, pause_duration, text)

        prior_turns = self._turns.get_last_n_turns(session_id, n=1)
        prev_text = prior_turns[0]["text"] if prior_turns else None
        prev_ended_at = prior_turns[0]["ended_at"] if prior_turns else None
        gap_seconds = (time.time() - prev_ended_at) if prev_ended_at else 0.0
        continuity = self._continuity.analyze(prev_text, text, gap_seconds=gap_seconds)

        tone_result = self._tone.detect(text)
        recommended_tone = self._tone.recommend_response_tone(tone_result["tone"])

        current = self._turns.get_current_turn(session_id)
        turn_id = current["turn_id"] if current else None

        if timing["decision"] == DECISION_RESPOND:
            self._log_event(
                session_id,
                turn_id,
                "utterance_complete",
                tone=tone_result["tone"],
                is_continuation=continuity["is_continuation"],
                topic_shift_score=continuity["topic_shift_score"],
                details={
                    "pause_id": timing["pause_id"],
                    "wait_threshold_used": timing["wait_threshold_used"],
                    "tone_confidence": tone_result["confidence"],
                },
            )

        return {
            "should_respond": timing["decision"] == DECISION_RESPOND,
            "pause_id": timing["pause_id"],
            "wait_threshold_used": timing["wait_threshold_used"],
            "is_continuation": continuity["is_continuation"],
            "topic_shift_score": continuity["topic_shift_score"],
            "has_reference": continuity["has_reference"],
            "tone": tone_result["tone"],
            "tone_confidence": tone_result["confidence"],
            "recommended_response_tone": recommended_tone,
        }

    def start_assistant_turn(
        self,
        session_id: str,
        expected_latency_seconds: float = 0.0,
        filler_reason: str = REASON_THINKING,
        tone: Optional[str] = None,
    ) -> Dict:
        """Closes the current user turn as completed and opens the
        assistant's. When expected_latency_seconds suggests the real
        response will take a noticeable moment, includes a filler
        phrase the caller can speak immediately while it's generated."""
        turn = self._turns.start_turn(session_id, SPEAKER_ASSISTANT)

        filler_text = None
        if expected_latency_seconds >= _FILLER_LATENCY_THRESHOLD_SECONDS:
            filler = self._filler.generate(reason=filler_reason, tone=tone)
            filler_text = filler["filler_text"]
            self._log_event(
                session_id,
                turn["turn_id"],
                "filler_used",
                filler_used=filler_text,
                details={"reason": filler_reason, "tone": tone},
            )

        turn["filler_text"] = filler_text
        return turn

    def end_assistant_turn(self, session_id: str, turn_id: int, text: str) -> Optional[Dict]:
        return self._turns.end_turn(turn_id, text=text)

    def report_response_outcome(self, pause_id: int, was_correct: bool) -> None:
        """Feeds back whether a past should_respond() call (from
        process_user_utterance()) was actually right, letting
        response_timer.py adjust that session's threshold."""
        self._timer.record_outcome(pause_id, was_correct)

    def get_session_summary(self, session_id: str, limit: int = 20) -> Dict:
        history = self._turns.get_history(session_id, limit=limit)
        events = self._get_events(session_id, limit=limit)
        barge_in_count = sum(1 for e in events if e["event_type"] == "barge_in")
        return {
            "session_id": session_id,
            "turn_count": len(history),
            "recent_turns": history,
            "barge_in_count": barge_in_count,
            "recent_events": events,
        }

    def _log_event(
        self,
        session_id: str,
        turn_id: Optional[int],
        event_type: str,
        tone: Optional[str] = None,
        is_continuation: Optional[bool] = None,
        topic_shift_score: Optional[float] = None,
        barge_in_detected: bool = False,
        barge_in_type: Optional[str] = None,
        filler_used: Optional[str] = None,
        details: Optional[Dict] = None,
    ) -> None:
        now = time.time()
        with self._lock:
            self._conn.execute(
                """INSERT INTO conversation_events
                   (session_id, turn_id, event_type, tone, is_continuation, topic_shift_score,
                    barge_in_detected, barge_in_type, filler_used, details_json, timestamp)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    session_id,
                    turn_id,
                    event_type,
                    tone,
                    None if is_continuation is None else int(is_continuation),
                    topic_shift_score,
                    int(barge_in_detected),
                    barge_in_type,
                    filler_used,
                    json.dumps(details or {}),
                    now,
                ),
            )
            self._conn.commit()

    def _get_events(self, session_id: str, limit: int = 20) -> List[Dict]:
        with self._lock:
            rows = self._conn.execute(
                """SELECT id, session_id, turn_id, event_type, tone, is_continuation, topic_shift_score,
                          barge_in_detected, barge_in_type, filler_used, details_json, timestamp
                   FROM conversation_events WHERE session_id = ? ORDER BY id DESC LIMIT ?""",
                (session_id, limit),
            ).fetchall()
        events = []
        for row in rows:
            (
                id_,
                sid,
                turn_id,
                event_type,
                tone,
                is_continuation,
                topic_shift_score,
                barge_in_detected,
                barge_in_type,
                filler_used,
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
                    "turn_id": turn_id,
                    "event_type": event_type,
                    "tone": tone,
                    "is_continuation": (None if is_continuation is None else bool(is_continuation)),
                    "topic_shift_score": topic_shift_score,
                    "barge_in_detected": bool(barge_in_detected),
                    "barge_in_type": barge_in_type,
                    "filler_used": filler_used,
                    "details": details,
                    "timestamp": timestamp,
                }
            )
        return events


def get_conversation_engine() -> ConversationEngine:
    """Process-wide ConversationEngine singleton."""
    global _instance
    if _instance is None:
        with _instance_lock:
            if _instance is None:
                _instance = ConversationEngine()
    return _instance
