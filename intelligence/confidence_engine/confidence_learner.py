"""
Confidence Learner (Phase 19.8 - Confidence Engine)
==================================================
Turns decision_gate.py's recorded outcomes into calibration checks -
"when we said 0.8 confidence, were we actually right 80% of the
time" - and nudges threshold_manager.py's thresholds when a risk
level's auto_execute bar is proving too loose or needlessly tight.
Same relationship as Phase 19.6's skill_improver.py to skill_store.py:
this module keeps its own stats and decides the promote/demote-style
calls, threshold_manager.py just stores whatever value results.

Adjustment is deliberately conservative and asymmetric: a string of
failed auto_execute decisions raises the bar (safer) as soon as
there's a handful of samples to act on, while a string of perfect
successes only lowers it by a small step and never below the
risk_level's original hardcoded floor - being slow to loosen and
quick to tighten is the right default for anything that gates
real actions.

Storage: database/confidence_history.db, table calibration_log.
"""

import sqlite3
import threading
import time
from pathlib import Path
from typing import Dict, List, Optional

from core.logger import get_logger
from intelligence.confidence_engine.threshold_manager import get_threshold_manager, get_hardcoded_default

logger = get_logger("ultron.confidence_learner")

DB_PATH = Path(__file__).resolve().parent.parent.parent / "database" / "confidence_history.db"

_instance: Optional["ConfidenceLearner"] = None
_instance_lock = threading.Lock()

_MIN_SAMPLES = 5  # don't adjust anything until this many outcomes exist for the slice
_TIGHTEN_FAILURE_RATE = 0.10  # auto_execute failing more than this often -> raise the bar
_TIGHTEN_STEP = 0.05
_LOOSEN_SUCCESS_RATE = 0.98  # auto_execute succeeding almost every time -> ease the bar, slowly
_LOOSEN_STEP = 0.02
_RECENT_WINDOW = 20  # only look at the most recent N outcomes for a slice, not all-time


class ConfidenceLearner:
    """Records (risk_level, action_type, confidence, decision,
    success) outcomes and adjusts threshold_manager.py's
    threshold_auto when the recent track record justifies it."""

    def __init__(self, db_path: Path = DB_PATH):
        self._db_path = db_path
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
        self._conn.execute("""CREATE TABLE IF NOT EXISTS calibration_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                risk_level TEXT,
                action_type TEXT,
                confidence REAL,
                decision TEXT,
                success INTEGER,
                timestamp REAL
            )""")
        self._conn.commit()
        self._thresholds = get_threshold_manager()

    def record(
        self, risk_level: str, action_type: Optional[str], confidence: float, decision: str, success: bool
    ) -> Dict:
        now = time.time()
        with self._lock:
            self._conn.execute(
                """INSERT INTO calibration_log
                   (risk_level, action_type, confidence, decision, success, timestamp)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (risk_level, action_type, confidence, decision, 1 if success else 0, now),
            )
            self._conn.commit()
        return self._maybe_adjust(risk_level, action_type)

    def get_calibration(
        self, risk_level: str, action_type: Optional[str] = None, decision: str = "auto_execute"
    ) -> Dict:
        """Recent success rate for a (risk_level, action_type,
        decision) slice - the diagnostic behind every adjustment this
        module makes, exposed directly for anyone who wants to see
        the numbers without waiting for an adjustment to happen."""
        rows = self._recent_outcomes(risk_level, action_type, decision)
        if not rows:
            return {
                "risk_level": risk_level,
                "action_type": action_type,
                "decision": decision,
                "sample_count": 0,
                "success_rate": None,
            }
        successes = sum(1 for r in rows if r)
        return {
            "risk_level": risk_level,
            "action_type": action_type,
            "decision": decision,
            "sample_count": len(rows),
            "success_rate": successes / len(rows),
        }

    def _maybe_adjust(self, risk_level: str, action_type: Optional[str]) -> Dict:
        """Checks the action_type-specific slice first (more precise
        signal), then falls back to the risk_level-wide slice if
        there aren't enough action_type-specific samples yet."""
        for scoped_action_type in ([action_type, None] if action_type else [None]):
            calibration = self.get_calibration(risk_level, scoped_action_type, "auto_execute")
            if calibration["sample_count"] < _MIN_SAMPLES:
                continue
            return self._apply_calibration(risk_level, scoped_action_type, calibration)
        return {"adjusted": False, "reason": "not enough samples yet"}

    def _apply_calibration(self, risk_level: str, action_type: Optional[str], calibration: Dict) -> Dict:
        success_rate = calibration["success_rate"]
        failure_rate = 1.0 - success_rate

        if failure_rate > _TIGHTEN_FAILURE_RATE:
            updated = self._thresholds.adjust_thresholds(risk_level, action_type=action_type, delta_auto=_TIGHTEN_STEP)
            logger.info(
                f"tightening auto-execute bar for risk={risk_level} "
                f"action_type={action_type}: failure_rate={failure_rate:.2f} "
                f"-> threshold_auto={updated['threshold_auto']:.2f}"
            )
            return {
                "adjusted": True,
                "direction": "tighten",
                "thresholds": updated,
                "success_rate": success_rate,
                "sample_count": calibration["sample_count"],
            }

        if success_rate >= _LOOSEN_SUCCESS_RATE:
            floor = get_hardcoded_default(risk_level)["threshold_auto"]
            current = self._thresholds.get_thresholds(risk_level, action_type)
            proposed_auto = max(floor, current["threshold_auto"] - _LOOSEN_STEP)
            if proposed_auto < current["threshold_auto"]:
                updated = self._thresholds.set_thresholds(
                    risk_level, proposed_auto, current["threshold_confirm"], action_type=action_type
                )
                logger.info(
                    f"easing auto-execute bar for risk={risk_level} "
                    f"action_type={action_type}: success_rate={success_rate:.2f} "
                    f"-> threshold_auto={updated['threshold_auto']:.2f}"
                )
                return {
                    "adjusted": True,
                    "direction": "loosen",
                    "thresholds": updated,
                    "success_rate": success_rate,
                    "sample_count": calibration["sample_count"],
                }

        return {
            "adjusted": False,
            "reason": "within acceptable calibration range",
            "success_rate": success_rate,
            "sample_count": calibration["sample_count"],
        }

    def _recent_outcomes(self, risk_level: str, action_type: Optional[str], decision: str) -> List[bool]:
        with self._lock:
            if action_type:
                rows = self._conn.execute(
                    """SELECT success FROM calibration_log
                       WHERE risk_level = ? AND action_type = ? AND decision = ?
                       ORDER BY id DESC LIMIT ?""",
                    (risk_level, action_type, decision, _RECENT_WINDOW),
                ).fetchall()
            else:
                rows = self._conn.execute(
                    """SELECT success FROM calibration_log
                       WHERE risk_level = ? AND decision = ?
                       ORDER BY id DESC LIMIT ?""",
                    (risk_level, decision, _RECENT_WINDOW),
                ).fetchall()
        return [bool(r[0]) for r in rows]


def get_confidence_learner() -> ConfidenceLearner:
    """Process-wide ConfidenceLearner singleton."""
    global _instance
    if _instance is None:
        with _instance_lock:
            if _instance is None:
                _instance = ConfidenceLearner()
    return _instance
