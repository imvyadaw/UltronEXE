"""
Next Action Predictor (Phase 19.2 - Intent Prediction)
=========================================================
A first-order action transition table like
PHASE_17_7_INTELLIGENCE/PREDICTIVE_ENGINE/next_action_predictor.py and
PHASE_18_9_1_AI_EVOLUTION/PREDICT/next_action.py, but scoped by the
*predicted intent* rather than global: "what usually follows
open_ide while the user is in a 'coding' intent" instead of "what
usually follows open_ide" full stop. That scoping is the point of
having a third one here - intent_predictor.py can ask this module for
a prediction conditioned on the intent it just inferred, which the
two earlier modules have no notion of.

Both earlier predictors are optional, import-guarded extra signals:
if either is importable, predict_next() blends its unscoped guess in
at a lower weight alongside this module's own intent-scoped table, so
predictions stay reasonable even before this table has much history
of its own. Neither import failing is an error - this module's own
table is always sufficient on its own.

Storage: database/intent_prediction.db, table action_transitions.
"""

import sqlite3
import threading
import time
from pathlib import Path
from typing import Dict, List, Optional

DB_PATH = Path(__file__).resolve().parent.parent.parent / "database" / "intent_prediction.db"

UNSCOPED_INTENT = ""  # sentinel for "no intent given" rows

_instance: Optional["NextActionPredictor"] = None
_instance_lock = threading.Lock()


class NextActionPredictor:
    """Intent-scoped first-order action transition table."""

    def __init__(self, db_path: Path = DB_PATH):
        self._db_path = db_path
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
        self._conn.execute("""CREATE TABLE IF NOT EXISTS action_transitions (
                intent TEXT,
                prev_action TEXT,
                next_action TEXT,
                count INTEGER,
                updated_at REAL,
                PRIMARY KEY (intent, prev_action, next_action)
            )""")
        self._conn.commit()

    # -- learning -----------------------------------------------------------
    def record_transition(self, prev_action: str, next_action: str, intent: Optional[str] = None) -> Dict:
        """Log that `next_action` followed `prev_action`, optionally scoped
        to the intent active at the time (unscoped if intent is None)."""
        if not prev_action or not next_action:
            return {"error": "prev_action and next_action required"}
        intent_key = intent or UNSCOPED_INTENT
        now = time.time()
        with self._lock:
            self._conn.execute(
                """INSERT INTO action_transitions (intent, prev_action, next_action, count, updated_at)
                   VALUES (?, ?, ?, 1, ?)
                   ON CONFLICT(intent, prev_action, next_action) DO UPDATE SET
                       count = count + 1, updated_at = excluded.updated_at""",
                (intent_key, prev_action, next_action, now),
            )
            self._conn.commit()
        return {"success": True}

    # -- prediction ------------------------------------------------------------
    def _own_scores(self, current_action: str, intent: Optional[str]) -> Dict[str, float]:
        intent_key = intent or UNSCOPED_INTENT
        with self._lock:
            cur = self._conn.execute(
                """SELECT next_action, count FROM action_transitions
                   WHERE prev_action = ? AND intent = ?""",
                (current_action, intent_key),
            )
            rows = cur.fetchall()
            if not rows and intent_key != UNSCOPED_INTENT:
                # fall back to unscoped history for this action if the
                # intent-scoped table has nothing yet
                cur = self._conn.execute(
                    """SELECT next_action, count FROM action_transitions
                       WHERE prev_action = ? AND intent = ?""",
                    (current_action, UNSCOPED_INTENT),
                )
                rows = cur.fetchall()
        total = sum(r[1] for r in rows)
        if total == 0:
            return {}
        return {action: count / total for action, count in rows}

    def _external_scores(self, current_action: str) -> Dict[str, float]:
        """Best-effort, import-guarded blend from the two pre-existing,
        unscoped predictors, if either is available in this codebase."""
        scores: Dict[str, float] = {}

        try:
            from predict.next_action import get_next_action

            result = get_next_action().predict(current_action)
            for entry in result.get("predictions", []):
                action, score = entry.get("action"), entry.get("score", 0.0)
                if action:
                    scores[action] = max(scores.get(action, 0.0), float(score))
        except Exception:
            from core.error_trace import log_swallowed as _lsw

            _lsw("intelligence.intent_prediction.next_action_predictor._external_scores")

        # PHASE_17_7_INTELLIGENCE/PREDICTIVE_ENGINE/next_action_predictor.py's
        # NextActionPredictor needs a caller-supplied BehaviorModeler instance
        # rather than exposing a module-level singleton, so there's nothing to
        # reach for generically here. use_legacy_behavior_modeler() below lets
        # a caller that *does* have one hand it in explicitly instead.

        return scores

    def use_legacy_behavior_modeler(self, current_action: str, modeler) -> Dict[str, float]:
        """Optional explicit bridge to a caller-supplied
        predictive_engine.behavior_modeler.BehaviorModeler
        instance, for callers that already have one built. Not called
        automatically by predict_next() since there's no process-wide
        instance to discover on its own."""
        try:
            from predictive_engine.next_action_predictor import NextActionPredictor as LegacyPredictor

            legacy = LegacyPredictor(modeler)
            predictions = legacy.predict(current_action) if hasattr(legacy, "predict") else []
            return {p.action: p.confidence for p in predictions}
        except Exception:
            return {}

    def predict_next(
        self, current_action: Optional[str] = None, intent: Optional[str] = None, top_n: int = 5
    ) -> List[Dict]:
        """Rank likely next actions given the current action and, if
        available, the current predicted intent. Blends this module's own
        intent-scoped table (weight 0.75) with any importable legacy
        predictors' unscoped guesses (weight 0.25)."""
        if not current_action:
            return []
        own = self._own_scores(current_action, intent)
        external = self._external_scores(current_action)

        actions = set(own) | set(external)
        ranked = []
        for action in actions:
            score = (own.get(action, 0.0) * 0.75) + (external.get(action, 0.0) * 0.25)
            ranked.append({"action": action, "confidence": round(score, 4)})
        ranked.sort(key=lambda r: r["confidence"], reverse=True)
        return ranked[:top_n]


def get_next_action_predictor() -> NextActionPredictor:
    """Process-wide NextActionPredictor singleton."""
    global _instance
    if _instance is None:
        with _instance_lock:
            if _instance is None:
                _instance = NextActionPredictor()
    return _instance
