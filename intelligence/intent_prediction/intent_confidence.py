"""
Intent Confidence (Phase 19.2 - Intent Prediction)
=====================================================
Shared scoring utilities used by every other module in this package:
combining several raw signal scores into one confidence value,
decaying a confidence as time passes since the observation that
produced it, and calibrating a raw score against how often this
predictor has actually been right about a given intent in the past.
Nothing here predicts anything itself - it just turns other modules'
raw numbers into something comparable and self-correcting.

Storage: database/intent_prediction.db, table confidence_log (one row
per predicted-vs-actual outcome a caller reports back via
record_outcome()).
"""

import sqlite3
import threading
import time
from pathlib import Path
from typing import Dict, List, Optional

DB_PATH = Path(__file__).resolve().parent.parent.parent / "database" / "intent_prediction.db"

DEFAULT_HALF_LIFE_SECONDS = 3600  # confidence halves every hour of staleness by default
DEFAULT_CONFIDENCE_THRESHOLD = 0.6

_instance: Optional["IntentConfidence"] = None
_instance_lock = threading.Lock()


class IntentConfidence:
    """Combine, decay, and calibrate confidence scores; track prediction accuracy."""

    def __init__(self, db_path: Path = DB_PATH):
        self._db_path = db_path
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
        self._conn.execute("""CREATE TABLE IF NOT EXISTS confidence_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                predicted_intent TEXT,
                actual_intent TEXT,
                confidence REAL,
                correct INTEGER,
                timestamp REAL
            )""")
        self._conn.commit()

    # -- pure scoring helpers (no DB) -----------------------------------------
    @staticmethod
    def combine(scores: List[float], weights: Optional[List[float]] = None) -> float:
        """Weighted average of several [0,1] signal scores into one,
        clamped to [0,1]. Missing/None entries in `scores` are skipped
        along with their matching weight."""
        pairs = [(s, w) for s, w in zip(scores, weights or [1.0] * len(scores)) if s is not None]
        if not pairs:
            return 0.0
        total_weight = sum(w for _, w in pairs)
        if total_weight == 0:
            return 0.0
        combined = sum(s * w for s, w in pairs) / total_weight
        return max(0.0, min(1.0, combined))

    @staticmethod
    def decay(confidence: float, seconds_elapsed: float, half_life_seconds: float = DEFAULT_HALF_LIFE_SECONDS) -> float:
        """Exponentially decay a confidence value as its supporting
        observation gets older - confidence halves every half_life_seconds."""
        if seconds_elapsed <= 0 or half_life_seconds <= 0:
            return max(0.0, min(1.0, confidence))
        factor = 0.5 ** (seconds_elapsed / half_life_seconds)
        return max(0.0, min(1.0, confidence * factor))

    @staticmethod
    def is_confident(confidence: float, threshold: float = DEFAULT_CONFIDENCE_THRESHOLD) -> bool:
        return confidence >= threshold

    # -- outcome tracking / calibration -----------------------------------------
    def record_outcome(self, predicted_intent: str, actual_intent: str, confidence: float) -> Dict:
        """Log what was predicted vs what actually happened, so
        accuracy_for()/calibrate() can learn whether this predictor
        over- or under-trusts a given intent."""
        if not predicted_intent or not actual_intent:
            return {"error": "predicted_intent and actual_intent required"}
        correct = predicted_intent == actual_intent
        with self._lock:
            self._conn.execute(
                """INSERT INTO confidence_log (predicted_intent, actual_intent, confidence, correct, timestamp)
                   VALUES (?, ?, ?, ?, ?)""",
                (predicted_intent, actual_intent, confidence, int(correct), time.time()),
            )
            self._conn.commit()
        return {"success": True, "correct": correct}

    def accuracy_for(self, intent: str, lookback: int = 50) -> float:
        """Fraction of the last `lookback` predictions of `intent` that
        turned out correct. Returns 0.5 (neutral - no adjustment) if
        there's no history yet for this intent."""
        with self._lock:
            cur = self._conn.execute(
                """SELECT correct FROM confidence_log WHERE predicted_intent = ?
                   ORDER BY timestamp DESC LIMIT ?""",
                (intent, lookback),
            )
            rows = cur.fetchall()
        if not rows:
            return 0.5
        return sum(r[0] for r in rows) / len(rows)

    def calibrate(self, intent: str, raw_confidence: float, lookback: int = 50) -> float:
        """Adjust a raw confidence score for `intent` toward this
        predictor's actual track record on that intent - a raw score
        pulled down if the predictor has historically been wrong about
        this intent more than it's been right, and left roughly alone
        if there's no track record yet."""
        accuracy = self.accuracy_for(intent, lookback=lookback)
        # blend: track record has half the say once there's meaningful history
        adjusted = (raw_confidence * 0.5) + (accuracy * 0.5)
        return max(0.0, min(1.0, adjusted))

    def stats(self, limit: int = 200) -> Dict:
        """Overall recent accuracy across all intents, plus how many
        outcomes have been logged."""
        with self._lock:
            cur = self._conn.execute("SELECT correct FROM confidence_log ORDER BY timestamp DESC LIMIT ?", (limit,))
            rows = cur.fetchall()
        if not rows:
            return {"count": 0, "accuracy": None}
        return {"count": len(rows), "accuracy": sum(r[0] for r in rows) / len(rows)}


def get_intent_confidence() -> IntentConfidence:
    """Process-wide IntentConfidence singleton."""
    global _instance
    if _instance is None:
        with _instance_lock:
            if _instance is None:
                _instance = IntentConfidence()
    return _instance
