"""
Decision Gate (Phase 19.8 - Confidence Engine)
==================================================
Single entry point for the confidence_engine/ package: turn a
pending action plus whatever's known about it into one of three
outcomes - auto_execute, confirm_with_user, or decline - and record
what was decided so confidence_learner.py can later check whether it
was right. Ties together:

    risk_assessor.py         - how risky is this action
    confidence_calculator.py - how confident are we it's the right call
    threshold_manager.py     - what confidence bar this risk level requires
    confidence_learner.py    - fed via record_outcome() once the real
                                result of a decision is known

Mirrors Phase 19.6/19.7's engine pattern (a thin orchestrator over
otherwise-independent sub-modules that still work fine called
directly) but takes the entry-point role itself rather than a
separate *_engine.py, since every decision that matters here ends up
at this gate regardless of which path led to it.

decide() is read/compute-only against risk_assessor.py and
confidence_calculator.py, and only writes to its own gate_decisions
table - it never touches threshold_manager.py's stored thresholds.
Only record_outcome(), by handing off to confidence_learner.py, can
ever move a threshold.

Storage: database/confidence_history.db, table gate_decisions (this
module's own table; the other four sub-modules each keep their own
tables, where they need one, in the same database file).

Purely additive - nothing in Phase 1-19.7 imports from here.
"""

import json
import sqlite3
import threading
import time
from pathlib import Path
from typing import Dict, List, Optional

from core.logger import get_logger
from intelligence.confidence_engine.risk_assessor import get_risk_assessor
from intelligence.confidence_engine.confidence_calculator import get_confidence_calculator
from intelligence.confidence_engine.threshold_manager import get_threshold_manager
from intelligence.confidence_engine.confidence_learner import get_confidence_learner

logger = get_logger("ultron.decision_gate")

DB_PATH = Path(__file__).resolve().parent.parent.parent / "database" / "confidence_history.db"

_instance: Optional["DecisionGate"] = None
_instance_lock = threading.Lock()

DECISION_AUTO_EXECUTE = "auto_execute"
DECISION_CONFIRM = "confirm_with_user"
DECISION_DECLINE = "decline"


class DecisionGate:
    """Orchestrates risk_assessor / confidence_calculator /
    threshold_manager into decide(), persists every decision, and
    routes recorded outcomes to confidence_learner.py."""

    def __init__(self, db_path: Path = DB_PATH):
        self._db_path = db_path
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
        self._conn.execute("""CREATE TABLE IF NOT EXISTS gate_decisions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                action_name TEXT,
                action_type TEXT,
                risk_level TEXT,
                risk_score REAL,
                confidence REAL,
                threshold_auto REAL,
                threshold_confirm REAL,
                decision TEXT,
                reasons_json TEXT,
                outcome_success INTEGER,
                outcome_recorded_at REAL,
                timestamp REAL
            )""")
        self._conn.commit()

        self._risk = get_risk_assessor()
        self._confidence = get_confidence_calculator()
        self._thresholds = get_threshold_manager()
        self._learner = get_confidence_learner()

    def decide(
        self,
        action_name: str,
        signals: Dict[str, float],
        params: Optional[Dict] = None,
        context: Optional[Dict] = None,
        action_type: Optional[str] = None,
    ) -> Dict:
        """Assess risk, compute confidence, look up the bar this risk
        level requires, and land on auto_execute / confirm_with_user
        / decline. Persists the decision and returns it with a
        decision_id that record_outcome() later needs."""
        risk = self._risk.assess(action_name, params=params, context=context)
        confidence = self._confidence.calculate(signals)
        thresholds = self._thresholds.get_thresholds(risk["risk_level"], action_type or action_name)

        score = confidence["confidence"]
        if score >= thresholds["threshold_auto"]:
            decision = DECISION_AUTO_EXECUTE
        elif score >= thresholds["threshold_confirm"]:
            decision = DECISION_CONFIRM
        else:
            decision = DECISION_DECLINE

        reasons = (
            risk["reasons"]
            + confidence["reasons"]
            + [
                f"confidence {score:.2f} vs auto={thresholds['threshold_auto']:.2f} "
                f"confirm={thresholds['threshold_confirm']:.2f}"
            ]
        )

        decision_id = self._save_decision(
            action_name, action_type or action_name, risk, confidence, thresholds, decision, reasons
        )
        logger.info(
            f"decision #{decision_id} for '{action_name}': {decision} "
            f"(risk={risk['risk_level']}, confidence={score:.2f})"
        )
        return {
            "decision_id": decision_id,
            "decision": decision,
            "risk_level": risk["risk_level"],
            "risk_score": risk["risk_score"],
            "confidence": score,
            "threshold_auto": thresholds["threshold_auto"],
            "threshold_confirm": thresholds["threshold_confirm"],
            "reasons": reasons,
        }

    def record_outcome(self, decision_id: int, success: bool) -> Optional[Dict]:
        """Log what actually happened for a past decision, and hand
        it to confidence_learner.py so miscalibrated thresholds can
        drift toward reality over time."""
        decision = self.get_decision(decision_id)
        if decision is None:
            return None

        now = time.time()
        with self._lock:
            self._conn.execute(
                """UPDATE gate_decisions SET outcome_success = ?, outcome_recorded_at = ?
                   WHERE id = ?""",
                (1 if success else 0, now, decision_id),
            )
            self._conn.commit()

        self._learner.record(
            risk_level=decision["risk_level"],
            action_type=decision["action_type"],
            confidence=decision["confidence"],
            decision=decision["decision"],
            success=success,
        )
        return self.get_decision(decision_id)

    def get_decision(self, decision_id: int) -> Optional[Dict]:
        with self._lock:
            row = self._conn.execute(
                """SELECT id, action_name, action_type, risk_level, risk_score, confidence,
                          threshold_auto, threshold_confirm, decision, reasons_json,
                          outcome_success, outcome_recorded_at, timestamp
                   FROM gate_decisions WHERE id = ?""",
                (decision_id,),
            ).fetchone()
        return self._row_to_decision(row) if row else None

    def list_decisions(self, decision: Optional[str] = None, limit: int = 50) -> List[Dict]:
        with self._lock:
            if decision:
                rows = self._conn.execute(
                    """SELECT id, action_name, action_type, risk_level, risk_score, confidence,
                              threshold_auto, threshold_confirm, decision, reasons_json,
                              outcome_success, outcome_recorded_at, timestamp
                       FROM gate_decisions WHERE decision = ? ORDER BY id DESC LIMIT ?""",
                    (decision, limit),
                ).fetchall()
            else:
                rows = self._conn.execute(
                    """SELECT id, action_name, action_type, risk_level, risk_score, confidence,
                              threshold_auto, threshold_confirm, decision, reasons_json,
                              outcome_success, outcome_recorded_at, timestamp
                       FROM gate_decisions ORDER BY id DESC LIMIT ?""",
                    (limit,),
                ).fetchall()
        return [self._row_to_decision(r) for r in rows]

    def _save_decision(
        self,
        action_name: str,
        action_type: str,
        risk: Dict,
        confidence: Dict,
        thresholds: Dict,
        decision: str,
        reasons: List[str],
    ) -> int:
        now = time.time()
        with self._lock:
            cur = self._conn.execute(
                """INSERT INTO gate_decisions
                   (action_name, action_type, risk_level, risk_score, confidence,
                    threshold_auto, threshold_confirm, decision, reasons_json,
                    outcome_success, outcome_recorded_at, timestamp)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL, ?)""",
                (
                    action_name,
                    action_type,
                    risk["risk_level"],
                    risk["risk_score"],
                    confidence["confidence"],
                    thresholds["threshold_auto"],
                    thresholds["threshold_confirm"],
                    decision,
                    json.dumps(reasons),
                    now,
                ),
            )
            self._conn.commit()
            return cur.lastrowid

    @staticmethod
    def _row_to_decision(row) -> Dict:
        (
            id_,
            action_name,
            action_type,
            risk_level,
            risk_score,
            confidence,
            threshold_auto,
            threshold_confirm,
            decision,
            reasons_json,
            outcome_success,
            outcome_recorded_at,
            timestamp,
        ) = row
        try:
            reasons = json.loads(reasons_json) if reasons_json else []
        except Exception:
            reasons = []
        return {
            "decision_id": id_,
            "action_name": action_name,
            "action_type": action_type,
            "risk_level": risk_level,
            "risk_score": risk_score,
            "confidence": confidence,
            "threshold_auto": threshold_auto,
            "threshold_confirm": threshold_confirm,
            "decision": decision,
            "reasons": reasons,
            "outcome_success": (None if outcome_success is None else bool(outcome_success)),
            "outcome_recorded_at": outcome_recorded_at,
            "timestamp": timestamp,
        }


def get_decision_gate() -> DecisionGate:
    """Process-wide DecisionGate singleton."""
    global _instance
    if _instance is None:
        with _instance_lock:
            if _instance is None:
                _instance = DecisionGate()
    return _instance
