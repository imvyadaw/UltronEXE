"""
Model Trainer (Phase 23.9 - Cognitive Reasoning Layer)
=========================================================
Final stage of the Phase 23 cognitive loop (see intent_analyzer.py's
header for the full pipeline diagram). learning_engine.py logs raw
(context_type, context_key, success) outcomes and derives human-
readable lessons from them; this module turns that same outcome
history into a small numeric weight table - one confidence weight
per (context_type, context_key) - that decision_engine.py or any
other caller can query cheaply (predict_weight()) without re-deriving
it from scratch every time.

Deliberately NOT a deep-learning trainer - there's no guarantee a
heavy ML stack (torch/tensorflow) is installed in every Ultron
environment, and this doesn't need one. train() uses:
    - scikit-learn's LogisticRegression when sklearn is importable
      (one-feature model: recency-weighted success rate -> a smoothed
      probability), for a slightly better-calibrated weight than raw
      counting alone.
    - a pure-Python Laplace-smoothed success rate otherwise - zero
      extra dependencies, always available, close enough for how this
      weight is actually used (a soft bias on decision_engine.py's
      confidence, not a hard threshold on its own).
Both paths produce the same output shape, so callers never need to
know which one actually ran.

Storage: database/model_trainer.db, table model_weights (the queryable
table) - plus a JSON snapshot written to storage/exports/ on every
train() call, for anyone who wants to inspect or ship the weights
outside of sqlite.
"""

import json
import sqlite3
import threading
import time
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Optional

try:
    from core.logger import get_logger

    logger = get_logger("ultron.model_trainer")
except Exception:  # pragma: no cover
    import logging

    logger = logging.getLogger("ultron.model_trainer")
    if not logger.handlers:
        logging.basicConfig(level=logging.INFO)

try:
    from intelligence.learning_engine import get_learning_engine
except Exception as exc:  # pragma: no cover
    get_learning_engine = None
    logger.warning(f"[model_trainer] intelligence.learning_engine unavailable, nothing to train on: {exc}")

try:
    from sklearn.linear_model import LogisticRegression
    import numpy as np

    _SKLEARN_AVAILABLE = True
except Exception:
    LogisticRegression = None
    np = None
    _SKLEARN_AVAILABLE = False

try:
    from config import STORAGE_DIR

    _EXPORT_DIR = STORAGE_DIR / "exports"
except Exception:  # pragma: no cover
    _EXPORT_DIR = Path(__file__).resolve().parent.parent / "storage" / "exports"

DB_PATH = Path(__file__).resolve().parent.parent / "database" / "model_trainer.db"
EXPORT_PATH = _EXPORT_DIR / "phase23_model_weights.json"

_instance: Optional["ModelTrainer"] = None
_instance_lock = threading.Lock()

_LAPLACE_ALPHA = 1.0  # smoothing: (successes + alpha) / (total + 2*alpha)
_DEFAULT_WEIGHT = 0.5


class ModelTrainer:
    """train() -> refreshes the weight table from learning_engine's outcomes;
    predict_weight(context_type, context_key) -> cheap lookup afterwards."""

    def __init__(self, db_path: Path = DB_PATH):
        self._db_path = db_path
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
        self._conn.execute("""CREATE TABLE IF NOT EXISTS model_weights (
                context_type TEXT,
                context_key TEXT,
                weight REAL,
                sample_count INTEGER,
                method TEXT,
                trained_at REAL,
                PRIMARY KEY (context_type, context_key)
            )""")
        self._conn.execute("""CREATE TABLE IF NOT EXISTS training_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                context_type TEXT,
                keys_trained INTEGER,
                method TEXT,
                timestamp REAL
            )""")
        self._conn.commit()
        self._learning = get_learning_engine() if get_learning_engine else None

    def train(self, context_type: Optional[str] = None) -> Dict:
        """Rebuild the weight table from learning_engine's outcome
        history, optionally scoped to one context_type. Returns a
        summary; the table itself is what callers should actually use
        via predict_weight()."""
        if self._learning is None:
            return {"error": "learning_engine unavailable - nothing to train on"}

        outcomes = self._learning.outcomes_for_training(context_type=context_type, limit=2000)
        if not outcomes:
            return {"trained": False, "reason": "no outcomes recorded yet"}

        grouped: Dict[tuple, List[bool]] = defaultdict(list)
        for o in outcomes:
            grouped[(o["context_type"], o["context_key"])].append(o["success"])

        method = "logistic_regression" if _SKLEARN_AVAILABLE else "laplace_smoothed_rate"
        now = time.time()
        weights = {}
        with self._lock:
            for (ctype, ckey), successes in grouped.items():
                weight = self._compute_weight(successes)
                weights[f"{ctype}::{ckey}"] = {"weight": weight, "sample_count": len(successes)}
                self._conn.execute(
                    """INSERT INTO model_weights (context_type, context_key, weight, sample_count, method, trained_at)
                       VALUES (?, ?, ?, ?, ?, ?)
                       ON CONFLICT(context_type, context_key) DO UPDATE SET
                         weight = excluded.weight, sample_count = excluded.sample_count,
                         method = excluded.method, trained_at = excluded.trained_at""",
                    (ctype, ckey, weight, len(successes), method, now),
                )
            self._conn.execute(
                """INSERT INTO training_runs (context_type, keys_trained, method, timestamp)
                   VALUES (?, ?, ?, ?)""",
                (context_type, len(grouped), method, now),
            )
            self._conn.commit()

        self._export_snapshot(weights, method, now)
        logger.info(f"[model_trainer] trained {len(grouped)} key(s) using {method}")
        return {"trained": True, "keys_trained": len(grouped), "method": method, "weights": weights}

    @staticmethod
    def _compute_weight(successes: List[bool]) -> float:
        """One scalar weight in [0, 1] per key: how much decision_engine.py
        (or any caller) should trust this key based on its track record."""
        if _SKLEARN_AVAILABLE and len(successes) >= 4:
            try:
                # Single feature (recency index) -> success label; the point
                # isn't a rich model, just a smoother probability estimate
                # than raw counting once there's enough history to fit on.
                x = np.arange(len(successes)).reshape(-1, 1)
                y = np.array([1 if s else 0 for s in successes])
                if len(set(y.tolist())) < 2:
                    # Degenerate case (all same label) - LogisticRegression
                    # can't fit this; fall through to the smoothed rate.
                    raise ValueError("single-class outcome history")
                model = LogisticRegression()
                model.fit(x, y)
                prob = float(model.predict_proba([[len(successes)]])[0][1])
                return max(0.0, min(1.0, prob))
            except Exception as e:
                logger.debug(f"[model_trainer] logistic regression fit failed, using smoothed rate: {e}")

        successes_count = sum(1 for s in successes if s)
        total = len(successes)
        return (successes_count + _LAPLACE_ALPHA) / (total + 2 * _LAPLACE_ALPHA)

    def predict_weight(self, context_type: str, context_key: str) -> float:
        """Cheap lookup of the last-trained weight for a key. Returns
        _DEFAULT_WEIGHT (neutral) if nothing's been trained for it yet -
        never raises, safe to call speculatively."""
        with self._lock:
            row = self._conn.execute(
                "SELECT weight FROM model_weights WHERE context_type = ? AND context_key = ?",
                (context_type, context_key),
            ).fetchone()
        return float(row[0]) if row else _DEFAULT_WEIGHT

    def all_weights(self, context_type: Optional[str] = None, limit: int = 100) -> List[Dict]:
        with self._lock:
            if context_type:
                rows = self._conn.execute(
                    """SELECT context_type, context_key, weight, sample_count, method, trained_at
                       FROM model_weights WHERE context_type = ? ORDER BY trained_at DESC LIMIT ?""",
                    (context_type, limit),
                ).fetchall()
            else:
                rows = self._conn.execute(
                    """SELECT context_type, context_key, weight, sample_count, method, trained_at
                       FROM model_weights ORDER BY trained_at DESC LIMIT ?""",
                    (limit,),
                ).fetchall()
        return [
            {
                "context_type": r[0],
                "context_key": r[1],
                "weight": r[2],
                "sample_count": r[3],
                "method": r[4],
                "trained_at": r[5],
            }
            for r in rows
        ]

    def _export_snapshot(self, weights: Dict, method: str, trained_at: float) -> None:
        """Best-effort JSON export - failure here (e.g. read-only
        filesystem) should never break train() itself."""
        try:
            EXPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
            EXPORT_PATH.write_text(
                json.dumps({"method": method, "trained_at": trained_at, "weights": weights}, indent=2, default=str),
                encoding="utf-8",
            )
        except Exception as e:
            logger.debug(f"[model_trainer] weight snapshot export skipped: {e}")


def get_model_trainer() -> ModelTrainer:
    """Process-wide ModelTrainer singleton."""
    global _instance
    if _instance is None:
        with _instance_lock:
            if _instance is None:
                _instance = ModelTrainer()
    return _instance
