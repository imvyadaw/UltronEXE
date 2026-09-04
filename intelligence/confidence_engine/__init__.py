"""
Confidence Engine (Phase 19.8)
=============================
Decides, for any pending action, whether ULTRON should just do it,
check with the user first, or decline outright - and learns from
whether those calls were actually right. All backed by a shared
database at database/confidence_history.db:

    risk_assessor.py         - classifies an action's risk level
                                (low/medium/high/critical) from its
                                name, params, and context
    confidence_calculator.py - combines whatever signals are known
                                about a decision into one confidence
                                score in [0, 1]
    threshold_manager.py     - stores and serves the confidence bar
                                each risk level (or specific
                                action_type) requires for auto-execute
                                vs confirm vs decline
    confidence_learner.py    - checks recent outcomes against what
                                was predicted and nudges thresholds
                                when the track record justifies it
    decision_gate.py         - single entry point tying all of the
                                above together

Usage:
    from intelligence.confidence_engine import get_decision_gate
    gate = get_decision_gate()

    result = gate.decide(
        "delete_file",
        signals={"source_reliability": 0.9, "historical_success_rate": 0.8, "ambiguity": 0.1},
        params={"path": "old_log.txt"},
    )
    # result["decision"] -> "auto_execute" / "confirm_with_user" / "decline"

    # once the real outcome is known:
    gate.record_outcome(result["decision_id"], success=True)

Each sub-module also exposes its own get_x() singleton and can be
used directly without going through decision_gate.py - e.g. call
risk_assessor.py alone just to check how risky an action would be,
with no decision or persistence involved.

Purely additive - nothing in Phase 1-19.7 imports from here.
"""

from intelligence.confidence_engine.risk_assessor import RiskAssessor, get_risk_assessor
from intelligence.confidence_engine.confidence_calculator import ConfidenceCalculator, get_confidence_calculator
from intelligence.confidence_engine.threshold_manager import ThresholdManager, get_threshold_manager
from intelligence.confidence_engine.confidence_learner import ConfidenceLearner, get_confidence_learner
from intelligence.confidence_engine.decision_gate import (
    DecisionGate,
    get_decision_gate,
    DECISION_AUTO_EXECUTE,
    DECISION_CONFIRM,
    DECISION_DECLINE,
)

__all__ = [
    "DecisionGate",
    "get_decision_gate",
    "DECISION_AUTO_EXECUTE",
    "DECISION_CONFIRM",
    "DECISION_DECLINE",
    "RiskAssessor",
    "get_risk_assessor",
    "ConfidenceCalculator",
    "get_confidence_calculator",
    "ThresholdManager",
    "get_threshold_manager",
    "ConfidenceLearner",
    "get_confidence_learner",
]
