"""
Learning Engine (Phase 23.7 - Cognitive Reasoning Layer)
=========================================================
Seventh stage of the Phase 23 cognitive loop (see intent_analyzer.py's
header for the full pipeline diagram). A single place every other
Phase 23 module can report an outcome to - decision_engine.py's step
results, self_critique.py's flawed-output flags, verification_engine's
contradicted claims - keyed by (context_type, context_key), e.g.
("decision_engine_step", "open browser and check email"). Aggregates
those into a running success rate per key and, once there's enough
signal, a short plain-English "lesson" other modules can read back
before repeating a similar step.

Distinct from intelligence.confidence_engine.confidence_learner.py,
which only calibrates decision_gate.py's own risk-level thresholds.
This module is deliberately more general - any (context_type,
context_key) pair, not just gate decisions - and produces a *readable*
lesson string rather than adjusting a numeric threshold. model_trainer.py
(final stage) is what turns this module's accumulated outcomes into
an updated weight table for decision_engine.py to consult.

Storage: database/learning_engine.db, tables outcomes / lessons.
"""

import json
import sqlite3
import threading
import time
from pathlib import Path
from typing import Dict, List, Optional

try:
    from core.logger import get_logger

    logger = get_logger("ultron.learning_engine")
except Exception:  # pragma: no cover
    import logging

    logger = logging.getLogger("ultron.learning_engine")
    if not logger.handlers:
        logging.basicConfig(level=logging.INFO)

DB_PATH = Path(__file__).resolve().parent.parent / "database" / "learning_engine.db"

_instance: Optional["LearningEngine"] = None
_instance_lock = threading.Lock()

_MIN_SAMPLES_FOR_LESSON = 3
_RECENT_WINDOW = 20
_LOW_SUCCESS_RATE = 0.4
_HIGH_SUCCESS_RATE = 0.9


class LearningEngine:
    """record_outcome(...) -> logs + derives a lesson; get_lesson(...) reads it back."""

    def __init__(self, db_path: Path = DB_PATH):
        self._db_path = db_path
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
        self._conn.execute("""CREATE TABLE IF NOT EXISTS outcomes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                context_type TEXT,
                context_key TEXT,
                success INTEGER,
                details_json TEXT,
                timestamp REAL
            )""")
        self._conn.execute("""CREATE TABLE IF NOT EXISTS lessons (
                context_type TEXT,
                context_key TEXT,
                lesson TEXT,
                success_rate REAL,
                sample_count INTEGER,
                updated_at REAL,
                PRIMARY KEY (context_type, context_key)
            )""")
        self._conn.commit()

    def record_outcome(
        self, context_type: str, context_key: str, success: bool, details: Optional[Dict] = None
    ) -> Dict:
        """Log one outcome and refresh the derived lesson for this
        (context_type, context_key) pair if there's now enough signal
        to say something useful."""
        if not context_type or not context_key:
            return {"error": "context_type and context_key required"}

        now = time.time()
        with self._lock:
            self._conn.execute(
                """INSERT INTO outcomes (context_type, context_key, success, details_json, timestamp)
                   VALUES (?, ?, ?, ?, ?)""",
                (context_type, context_key, int(bool(success)), json.dumps(details or {}, default=str), now),
            )
            self._conn.commit()

        return self._refresh_lesson(context_type, context_key)

    def _refresh_lesson(self, context_type: str, context_key: str) -> Dict:
        with self._lock:
            rows = self._conn.execute(
                """SELECT success FROM outcomes WHERE context_type = ? AND context_key = ?
                   ORDER BY id DESC LIMIT ?""",
                (context_type, context_key, _RECENT_WINDOW),
            ).fetchall()

        sample_count = len(rows)
        if sample_count < _MIN_SAMPLES_FOR_LESSON:
            return {"lesson_updated": False, "reason": "not enough samples yet", "sample_count": sample_count}

        success_rate = sum(r[0] for r in rows) / sample_count
        lesson = self._derive_lesson(context_key, success_rate, sample_count)

        now = time.time()
        with self._lock:
            self._conn.execute(
                """INSERT INTO lessons (context_type, context_key, lesson, success_rate, sample_count, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?)
                   ON CONFLICT(context_type, context_key) DO UPDATE SET
                     lesson = excluded.lesson, success_rate = excluded.success_rate,
                     sample_count = excluded.sample_count, updated_at = excluded.updated_at""",
                (context_type, context_key, lesson, success_rate, sample_count, now),
            )
            self._conn.commit()

        logger.info(
            f"[learning_engine] lesson updated for {context_type}/{context_key[:60]}: "
            f"success_rate={success_rate:.2f} ({sample_count} samples)"
        )
        return {"lesson_updated": True, "lesson": lesson, "success_rate": success_rate, "sample_count": sample_count}

    @staticmethod
    def _derive_lesson(context_key: str, success_rate: float, sample_count: int) -> str:
        if success_rate >= _HIGH_SUCCESS_RATE:
            return f"'{context_key}' has succeeded reliably ({success_rate:.0%} of {sample_count} recent attempts) - safe to trust."
        if success_rate <= _LOW_SUCCESS_RATE:
            return f"'{context_key}' has failed often ({success_rate:.0%} success over {sample_count} recent attempts) - treat with extra caution or confirm first."
        return f"'{context_key}' has mixed results ({success_rate:.0%} success over {sample_count} recent attempts) - no strong signal either way yet."

    def get_lesson(self, context_type: str, context_key: str) -> Dict:
        """Read back the current lesson for a key, or an empty-but-valid
        result if nothing's been learned about it yet."""
        with self._lock:
            row = self._conn.execute(
                """SELECT lesson, success_rate, sample_count, updated_at FROM lessons
                   WHERE context_type = ? AND context_key = ?""",
                (context_type, context_key),
            ).fetchone()
        if row is None:
            return {
                "context_type": context_type,
                "context_key": context_key,
                "lesson": None,
                "success_rate": None,
                "sample_count": 0,
            }
        return {
            "context_type": context_type,
            "context_key": context_key,
            "lesson": row[0],
            "success_rate": row[1],
            "sample_count": row[2],
            "updated_at": row[3],
        }

    def all_lessons(self, context_type: Optional[str] = None, limit: int = 50) -> List[Dict]:
        with self._lock:
            if context_type:
                rows = self._conn.execute(
                    """SELECT context_type, context_key, lesson, success_rate, sample_count, updated_at
                       FROM lessons WHERE context_type = ? ORDER BY updated_at DESC LIMIT ?""",
                    (context_type, limit),
                ).fetchall()
            else:
                rows = self._conn.execute(
                    """SELECT context_type, context_key, lesson, success_rate, sample_count, updated_at
                       FROM lessons ORDER BY updated_at DESC LIMIT ?""",
                    (limit,),
                ).fetchall()
        return [
            {
                "context_type": r[0],
                "context_key": r[1],
                "lesson": r[2],
                "success_rate": r[3],
                "sample_count": r[4],
                "updated_at": r[5],
            }
            for r in rows
        ]

    def outcomes_for_training(self, context_type: Optional[str] = None, limit: int = 500) -> List[Dict]:
        """Raw outcome rows for model_trainer.py to consume - kept
        separate from all_lessons() since the trainer wants individual
        samples, not the aggregated summary."""
        with self._lock:
            if context_type:
                rows = self._conn.execute(
                    """SELECT context_type, context_key, success, details_json, timestamp
                       FROM outcomes WHERE context_type = ? ORDER BY id DESC LIMIT ?""",
                    (context_type, limit),
                ).fetchall()
            else:
                rows = self._conn.execute(
                    """SELECT context_type, context_key, success, details_json, timestamp
                       FROM outcomes ORDER BY id DESC LIMIT ?""",
                    (limit,),
                ).fetchall()
        out = []
        for context_type_, context_key, success, details_json, ts in rows:
            try:
                details = json.loads(details_json)
            except Exception:
                details = {}
            out.append(
                {
                    "context_type": context_type_,
                    "context_key": context_key,
                    "success": bool(success),
                    "details": details,
                    "timestamp": ts,
                }
            )
        return out


def get_learning_engine() -> LearningEngine:
    """Process-wide LearningEngine singleton."""
    global _instance
    if _instance is None:
        with _instance_lock:
            if _instance is None:
                _instance = LearningEngine()
    return _instance
