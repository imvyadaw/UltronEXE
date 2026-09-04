"""
Response Timer (Phase 20 - Conversation Layer)
==================================================
Decides whether a silence after the user stops talking means they're
actually done (time to respond) or just a mid-thought pause (keep
waiting) - and adjusts how long it waits per session as it learns
whether past calls were right, the same way threshold_manager.py /
confidence_learner.py split storage from adjustment in Phase 19.8,
just combined into one module here since endpointing is the only
thing this package needs adaptive thresholds for.

should_respond() combines two things: the raw pause_duration against
a per-session wait_threshold (stored, falling back to a hardcoded
default), and a quick syntactic check on text_so_far - a trailing
conjunction ("and", "but", "so", "because", ...) or an obviously
unfinished clause extends how long it's willing to wait, while a
clear sentence-ending question mark shortens it. record_outcome()
lets a caller report after the fact whether the decision was right
(cut the user off vs made them wait too long) and nudges that
session's threshold accordingly, clamped to a safety floor/ceiling so
it never drifts to something unusable.

Storage: database/conversation_history.db, table pause_events (every
should_respond() call, for history/debugging) and table
timing_thresholds (one row per session_id, the adaptive value itself).
"""

import sqlite3
import threading
import time
from pathlib import Path
from typing import Dict, List, Optional

DB_PATH = Path(__file__).resolve().parent.parent.parent / "database" / "conversation_history.db"

_instance: Optional["ResponseTimer"] = None
_instance_lock = threading.Lock()

# floor/ceiling the adaptive threshold can never cross, regardless of
# how the learning nudges accumulate - same spirit as
# threshold_manager.py's hardcoded per-risk-level floor in 19.8
_DEFAULT_WAIT_THRESHOLD = 0.8
_MIN_WAIT_THRESHOLD = 0.35
_MAX_WAIT_THRESHOLD = 2.5
_ADJUSTMENT_STEP = 0.05

_TRAILING_CONJUNCTIONS = ("and", "but", "so", "because", "or", "if", "when", "since", "although")

DECISION_RESPOND = "respond"
DECISION_WAIT = "wait"


class ResponseTimer:
    """Adaptive endpointing: should_respond() decides now, record_outcome()
    lets the decision inform the next one for that session."""

    def __init__(self, db_path: Path = DB_PATH):
        self._db_path = db_path
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
        self._conn.execute("""CREATE TABLE IF NOT EXISTS pause_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT,
                pause_duration REAL,
                text_so_far TEXT,
                threshold_used REAL,
                decision TEXT,
                outcome_correct INTEGER,
                outcome_recorded_at REAL,
                timestamp REAL
            )""")
        self._conn.execute("""CREATE TABLE IF NOT EXISTS timing_thresholds (
                session_id TEXT PRIMARY KEY,
                wait_threshold REAL,
                updated_at REAL
            )""")
        self._conn.commit()

    def get_wait_threshold(self, session_id: Optional[str]) -> float:
        if not session_id:
            return _DEFAULT_WAIT_THRESHOLD
        with self._lock:
            row = self._conn.execute(
                "SELECT wait_threshold FROM timing_thresholds WHERE session_id = ?", (session_id,)
            ).fetchone()
        return row[0] if row else _DEFAULT_WAIT_THRESHOLD

    def should_respond(self, session_id: Optional[str], pause_duration: float, text_so_far: str = "") -> Dict:
        threshold = self.get_wait_threshold(session_id)
        reasons: List[str] = [f"base wait_threshold for session is {threshold:.2f}s"]

        stripped = (text_so_far or "").strip()
        effective_threshold = threshold
        if stripped.endswith("?"):
            effective_threshold *= 0.7
            reasons.append("text ends with '?' - shortening threshold, likely a complete question")
        elif self._ends_with_trailing_conjunction(stripped):
            effective_threshold *= 1.6
            reasons.append("text trails off on a conjunction - extending threshold, likely unfinished")
        elif stripped and stripped[-1] not in ".!?":
            effective_threshold *= 1.2
            reasons.append("text has no terminal punctuation - extending threshold slightly")

        decision = DECISION_RESPOND if pause_duration >= effective_threshold else DECISION_WAIT
        reasons.append(f"pause_duration {pause_duration:.2f}s vs effective threshold {effective_threshold:.2f}s")

        pause_id = self._save_pause_event(session_id, pause_duration, stripped, effective_threshold, decision)
        return {
            "pause_id": pause_id,
            "decision": decision,
            "wait_threshold_used": round(effective_threshold, 3),
            "base_wait_threshold": threshold,
            "reasons": reasons,
        }

    def record_outcome(self, pause_id: int, was_correct: bool) -> None:
        """Report whether a past should_respond() call got it right,
        and nudge that session's threshold accordingly: responding too
        early (should have waited) pushes the threshold up, waiting
        too long (should have responded) pushes it down. A correct
        call leaves the threshold untouched."""
        with self._lock:
            row = self._conn.execute(
                "SELECT session_id, decision FROM pause_events WHERE id = ?", (pause_id,)
            ).fetchone()
            if row is None:
                return
            session_id, decision = row
            now = time.time()
            self._conn.execute(
                "UPDATE pause_events SET outcome_correct = ?, outcome_recorded_at = ? WHERE id = ?",
                (1 if was_correct else 0, now, pause_id),
            )
            self._conn.commit()

        if was_correct or not session_id:
            return

        if decision == DECISION_RESPOND:
            self._adjust_threshold(session_id, _ADJUSTMENT_STEP)
        else:
            self._adjust_threshold(session_id, -_ADJUSTMENT_STEP)

    def _adjust_threshold(self, session_id: str, delta: float) -> float:
        current = self.get_wait_threshold(session_id)
        new_value = max(_MIN_WAIT_THRESHOLD, min(_MAX_WAIT_THRESHOLD, current + delta))
        now = time.time()
        with self._lock:
            self._conn.execute(
                """INSERT INTO timing_thresholds (session_id, wait_threshold, updated_at)
                   VALUES (?, ?, ?)
                   ON CONFLICT(session_id) DO UPDATE SET
                       wait_threshold = excluded.wait_threshold, updated_at = excluded.updated_at""",
                (session_id, new_value, now),
            )
            self._conn.commit()
        return new_value

    def get_recent_pauses(self, session_id: str, limit: int = 20) -> List[Dict]:
        with self._lock:
            rows = self._conn.execute(
                """SELECT id, session_id, pause_duration, text_so_far, threshold_used, decision,
                          outcome_correct, outcome_recorded_at, timestamp
                   FROM pause_events WHERE session_id = ? ORDER BY id DESC LIMIT ?""",
                (session_id, limit),
            ).fetchall()
        return [self._row_to_event(r) for r in rows]

    def _save_pause_event(
        self, session_id: Optional[str], pause_duration: float, text_so_far: str, threshold_used: float, decision: str
    ) -> int:
        now = time.time()
        with self._lock:
            cur = self._conn.execute(
                """INSERT INTO pause_events
                   (session_id, pause_duration, text_so_far, threshold_used, decision,
                    outcome_correct, outcome_recorded_at, timestamp)
                   VALUES (?, ?, ?, ?, ?, NULL, NULL, ?)""",
                (session_id, pause_duration, text_so_far, threshold_used, decision, now),
            )
            self._conn.commit()
            return cur.lastrowid

    @staticmethod
    def _ends_with_trailing_conjunction(text: str) -> bool:
        lowered = text.lower().rstrip(" .,!?")
        return any(lowered.endswith(f" {word}") or lowered == word for word in _TRAILING_CONJUNCTIONS)

    @staticmethod
    def _row_to_event(row) -> Dict:
        (
            id_,
            session_id,
            pause_duration,
            text_so_far,
            threshold_used,
            decision,
            outcome_correct,
            outcome_recorded_at,
            timestamp,
        ) = row
        return {
            "pause_id": id_,
            "session_id": session_id,
            "pause_duration": pause_duration,
            "text_so_far": text_so_far,
            "threshold_used": threshold_used,
            "decision": decision,
            "outcome_correct": (None if outcome_correct is None else bool(outcome_correct)),
            "outcome_recorded_at": outcome_recorded_at,
            "timestamp": timestamp,
        }


def get_response_timer() -> ResponseTimer:
    """Process-wide ResponseTimer singleton."""
    global _instance
    if _instance is None:
        with _instance_lock:
            if _instance is None:
                _instance = ResponseTimer()
    return _instance
