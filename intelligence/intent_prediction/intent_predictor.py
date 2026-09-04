"""
Intent Predictor (Phase 19.2 - Intent Prediction)
====================================================
Single entry point for the intent_prediction/ package: logs observed
(action, intent, context) events, and ties context_intent_mapper.py,
pattern_analyzer.py, goal_predictor.py, next_action_predictor.py, and
intent_confidence.py together into one predict() call that returns a
ranked list of candidate intents, a predicted next action, and any
goal the recent activity looks like it's building toward.

Relationship to intelligence.world_state (Phase 19.1): this module
sits directly on top of it - context_intent_mapper.py already pulls
live active_context/environment_state/task_state readings when no
explicit context is given, so callers can usually just call predict()
with no arguments during normal operation and get a live answer.

Storage: database/intent_prediction.db, table intent_events - this
module's own record of what was observed and when, which recent_*()
reads back to feed the other sub-modules.
"""

import json
import sqlite3
import threading
import time
from pathlib import Path
from typing import Dict, List, Optional

from core.logger import get_logger
from intelligence.intent_prediction.context_intent_mapper import get_context_intent_mapper
from intelligence.intent_prediction.goal_predictor import get_goal_predictor
from intelligence.intent_prediction.intent_confidence import get_intent_confidence
from intelligence.intent_prediction.next_action_predictor import get_next_action_predictor
from intelligence.intent_prediction.pattern_analyzer import get_pattern_analyzer

logger = get_logger("ultron.intent_predictor")

DB_PATH = Path(__file__).resolve().parent.parent.parent / "database" / "intent_prediction.db"

_instance: Optional["IntentPredictor"] = None
_instance_lock = threading.Lock()


class IntentPredictor:
    """Orchestrates the intent_prediction sub-modules into one predict/record API."""

    def __init__(self, db_path: Path = DB_PATH):
        self._db_path = db_path
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
        self._conn.execute("""CREATE TABLE IF NOT EXISTS intent_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                action TEXT,
                intent_label TEXT,
                context_json TEXT,
                timestamp REAL
            )""")
        self._conn.commit()

        self._mapper = get_context_intent_mapper()
        self._patterns = get_pattern_analyzer()
        self._goals = get_goal_predictor()
        self._next_action = get_next_action_predictor()
        self._confidence = get_intent_confidence()

        self._last_action: Optional[str] = None

    # -- observation / learning -----------------------------------------------
    def record_observation(self, action: str, intent_label: str, context: Optional[Dict] = None) -> Dict:
        """Log a confirmed (action, intent) pair - e.g. once a caller knows
        for certain what the user was doing - and feed it to every
        sub-module that learns from history: context_intent_mapper's
        learned associations, pattern_analyzer's sequence log, and
        next_action_predictor's intent-scoped transition table."""
        if not action or not intent_label:
            return {"error": "action and intent_label required"}

        resolved_context = context if context is not None else self._mapper.live_context()
        now = time.time()
        with self._lock:
            self._conn.execute(
                """INSERT INTO intent_events (action, intent_label, context_json, timestamp)
                   VALUES (?, ?, ?, ?)""",
                (action, intent_label, json.dumps(resolved_context, default=str), now),
            )
            self._conn.commit()

        self._mapper.record_observation(resolved_context, intent_label)
        self._patterns.record_intent(intent_label)
        if self._last_action:
            self._next_action.record_transition(self._last_action, action, intent=intent_label)
        self._last_action = action

        return {"success": True}

    def recent_intent_labels(self, limit: int = 10) -> List[str]:
        """Most recent recorded intent labels, chronological order (oldest
        of the window first, most recent last) - the shape
        pattern_analyzer.next_likely()/goal_predictor.infer_active_goal()
        expect."""
        with self._lock:
            cur = self._conn.execute("SELECT intent_label FROM intent_events ORDER BY id DESC LIMIT ?", (limit,))
            rows = cur.fetchall()
        return [r[0] for r in reversed(rows)]

    # -- prediction ----------------------------------------------------------
    def predict(self, context: Optional[Dict] = None, current_action: Optional[str] = None) -> Dict:
        """Predict the current intent, blending context heuristics with
        recent sequence patterns, then use that to predict the likely
        next action and any goal the activity looks like it's building
        toward. Returns:
            {
              "intents": [{"intent": ..., "confidence": ...}, ...],
              "top_intent": ... or None,
              "predicted_next_action": [{"action": ..., "confidence": ...}, ...],
              "active_goals": [...],
            }
        """
        context_scores = {r["intent"]: r["score"] for r in self._mapper.map_context(context)}

        recent = self.recent_intent_labels(limit=5)
        pattern_scores = {r["intent"]: r["score"] for r in self._patterns.next_likely(recent)} if recent else {}

        intents = set(context_scores) | set(pattern_scores)
        ranked = []
        for intent in intents:
            raw = self._confidence.combine(
                [context_scores.get(intent), pattern_scores.get(intent)],
                weights=[0.6, 0.4],
            )
            calibrated = self._confidence.calibrate(intent, raw)
            ranked.append({"intent": intent, "confidence": round(calibrated, 4)})
        ranked.sort(key=lambda r: r["confidence"], reverse=True)

        top_intent = ranked[0]["intent"] if ranked else None

        action_for_lookup = current_action or self._last_action
        predicted_next_action = (
            self._next_action.predict_next(action_for_lookup, intent=top_intent) if action_for_lookup else []
        )

        active_goals = self._goals.infer_active_goal(recent) if recent else []

        return {
            "intents": ranked,
            "top_intent": top_intent,
            "predicted_next_action": predicted_next_action,
            "active_goals": active_goals,
        }

    def report_actual_intent(self, predicted_intent: str, actual_intent: str, confidence: float) -> Dict:
        """Feedback hook: tell the predictor what the intent actually
        turned out to be, so intent_confidence.py's calibration improves
        over time. Purely optional - predict() works without ever being
        called back."""
        return self._confidence.record_outcome(predicted_intent, actual_intent, confidence)


def get_intent_predictor() -> IntentPredictor:
    """Process-wide IntentPredictor singleton."""
    global _instance
    if _instance is None:
        with _instance_lock:
            if _instance is None:
                _instance = IntentPredictor()
    return _instance
