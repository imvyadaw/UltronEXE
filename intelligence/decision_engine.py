"""
Decision Engine (Phase 23.4 - Cognitive Reasoning Layer)
=========================================================
Fourth stage of the Phase 23 cognitive loop (see intent_analyzer.py's
header for the full pipeline diagram). Takes one step out of
goal_planner.py's plan - a description plus a rough risk label - and
turns it into a concrete auto_execute / confirm_with_user / decline
call, the same three-way outcome intelligence.confidence_engine's
decision_gate.py already uses for individual actions.

Where possible this is a thin wrapper over decision_gate.py itself
(preferred - it already has calibrated thresholds and a learning
loop via confidence_learner.py). When that package isn't importable,
decide_step() falls back to a simple, conservative risk-label
heuristic so the cognitive loop still produces a usable decision
rather than breaking. Either way, every decision also folds in a
same-turn emotional read from emotional_analyzer.py when available:
a step that would otherwise auto-execute is downgraded to
confirm_with_user if the user seems frustrated right now - a rushed
irreversible action is the last thing that helps in that moment.

Storage: database/decision_engine.db, table step_decisions - kept
separate from decision_gate.py's own gate_decisions table since this
module may be deciding on plan steps that never go through the gate
at all (e.g. when confidence_engine isn't present).
"""

import json
import sqlite3
import threading
import time
from pathlib import Path
from typing import Dict, Optional

try:
    from core.logger import get_logger

    logger = get_logger("ultron.decision_engine")
except Exception:  # pragma: no cover
    import logging

    logger = logging.getLogger("ultron.decision_engine")
    if not logger.handlers:
        logging.basicConfig(level=logging.INFO)

try:
    from intelligence.confidence_engine.decision_gate import get_decision_gate
except Exception as exc:  # pragma: no cover
    get_decision_gate = None
    logger.warning(f"[decision_engine] confidence_engine.decision_gate unavailable, using heuristic fallback: {exc}")

DB_PATH = Path(__file__).resolve().parent.parent / "database" / "decision_engine.db"

_instance: Optional["DecisionEngine"] = None
_instance_lock = threading.Lock()

DECISION_AUTO_EXECUTE = "auto_execute"
DECISION_CONFIRM = "confirm_with_user"
DECISION_DECLINE = "decline"

# Heuristic fallback only - used when confidence_engine isn't available.
_RISK_TO_DECISION = {
    "low": DECISION_AUTO_EXECUTE,
    "medium": DECISION_CONFIRM,
    "high": DECISION_DECLINE,
}


class DecisionEngine:
    """decide_step(step, risk) -> {"decision", "reasons", "decision_id"}."""

    def __init__(self, db_path: Path = DB_PATH):
        self._db_path = db_path
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
        self._conn.execute("""CREATE TABLE IF NOT EXISTS step_decisions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                step TEXT,
                risk TEXT,
                decision TEXT,
                reasons_json TEXT,
                source TEXT,
                gate_decision_id INTEGER,
                outcome_success INTEGER,
                timestamp REAL
            )""")
        self._conn.commit()
        self._gate = get_decision_gate() if get_decision_gate else None

    def decide_step(
        self, step: str, risk: str = "medium", confidence: Optional[float] = None, context: Optional[Dict] = None
    ) -> Dict:
        """Decide what to do about one plan step. `risk` should match
        goal_planner.py's step risk label ("low"/"medium"/"high").
        `confidence` is optional (0-1); when omitted, a confidence is
        derived from the risk label alone so this still works without
        an upstream confidence score."""
        step = (step or "").strip()
        if not step:
            return {"error": "empty step"}
        risk = risk if risk in _RISK_TO_DECISION else "medium"
        confidence = confidence if confidence is not None else {"low": 0.9, "medium": 0.6, "high": 0.3}[risk]

        if self._gate is not None:
            decision, reasons, gate_decision_id, source = self._decide_via_gate(step, risk, confidence, context)
        else:
            decision, reasons, gate_decision_id, source = self._decide_heuristic(step, risk, confidence)

        decision, reasons = self._apply_emotional_guard(decision, reasons)

        decision_id = self._log_decision(step, risk, decision, reasons, source, gate_decision_id)
        return {
            "decision_id": decision_id,
            "decision": decision,
            "risk": risk,
            "confidence": confidence,
            "reasons": reasons,
            "source": source,
        }

    def _decide_via_gate(self, step: str, risk: str, confidence: float, context: Optional[Dict]):
        try:
            outcome = self._gate.decide(step, signals={"base": confidence}, context=context)
            return outcome["decision"], outcome["reasons"], outcome["decision_id"], "decision_gate"
        except Exception as e:
            logger.info(f"[decision_engine] decision_gate call failed, falling back to heuristic: {e}")
            return self._decide_heuristic(step, risk, confidence)

    @staticmethod
    def _decide_heuristic(step: str, risk: str, confidence: float):
        decision = _RISK_TO_DECISION[risk]
        reasons = [f"heuristic: risk={risk} -> {decision} (confidence_engine unavailable)"]
        return decision, reasons, None, "heuristic"

    @staticmethod
    def _apply_emotional_guard(decision: str, reasons: list) -> (str, list):
        """Downgrade auto_execute to confirm_with_user if the user looks
        frustrated in the current session - optional, best-effort, and
        never raises if emotional_analyzer.py isn't available."""
        if decision != DECISION_AUTO_EXECUTE:
            return decision, reasons
        try:
            from intelligence.emotional_analyzer import get_emotional_analyzer

            if get_emotional_analyzer().is_user_frustrated_recently():
                return DECISION_CONFIRM, reasons + ["downgraded from auto_execute: user seems frustrated right now"]
        except Exception:
            from core.error_trace import log_swallowed as _lsw

            _lsw("intelligence.decision_engine._apply_emotional_guard")
        return decision, reasons

    def _log_decision(
        self, step: str, risk: str, decision: str, reasons: list, source: str, gate_decision_id: Optional[int]
    ) -> int:
        now = time.time()
        with self._lock:
            cur = self._conn.execute(
                """INSERT INTO step_decisions (step, risk, decision, reasons_json, source, gate_decision_id, timestamp)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (step, risk, decision, json.dumps(reasons, default=str), source, gate_decision_id, now),
            )
            self._conn.commit()
            return cur.lastrowid

    def record_outcome(self, decision_id: int, success: bool) -> Dict:
        """Record whether a decided-on step actually succeeded. Feeds
        the outcome back to decision_gate.py's confidence_learner (when
        that decision went through the gate) and also best-effort
        reports it to learning_engine.py for the broader lessons store."""
        with self._lock:
            self._conn.execute(
                "UPDATE step_decisions SET outcome_success = ? WHERE id = ?",
                (int(bool(success)), decision_id),
            )
            self._conn.commit()
            row = self._conn.execute(
                "SELECT step, risk, decision, gate_decision_id FROM step_decisions WHERE id = ?",
                (decision_id,),
            ).fetchone()

        if row and row[3] is not None and self._gate is not None:
            try:
                self._gate.record_outcome(row[3], success)
            except Exception as e:
                logger.info(f"[decision_engine] could not forward outcome to decision_gate: {e}")

        if row:
            try:
                from intelligence.learning_engine import get_learning_engine

                get_learning_engine().record_outcome(
                    "decision_engine_step", row[0], success, {"risk": row[1], "decision": row[2]}
                )
            except Exception:
                from core.error_trace import log_swallowed as _lsw

                _lsw("intelligence.decision_engine.record_outcome")

        return {"decision_id": decision_id, "outcome_recorded": bool(row)}


def get_decision_engine() -> DecisionEngine:
    """Process-wide DecisionEngine singleton."""
    global _instance
    if _instance is None:
        with _instance_lock:
            if _instance is None:
                _instance = DecisionEngine()
    return _instance
