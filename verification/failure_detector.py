"""
Failure Detector (Phase 30 - Verification)
==============================================
verification_engine/ and intelligence/verification/success_evaluator.py
already classify individual checks into VERIFIED_SUCCESS /
VERIFIED_FAILURE / PARTIAL_SUCCESS / UNKNOWN (hardening/result_states.py)
- but nothing turns that classification into a *decision*. This
module is that decision layer core/orchestrator.py calls after every
step: given the ResultState (and how many times this same step has
already failed), should the run trigger
intelligence/self_healing/self_healing_engine.py, attempt
verification/rollback.py, hand off to planning/replanner.py, or just
log and continue.

Deliberately small - it does not re-verify anything itself (that's
verification_engine's job), it only routes an already-made
classification to the right next action.
"""

from typing import Dict, Optional

from core.logger import get_logger
from hardening.result_states import ResultState

logger = get_logger("ultron.verification.failure_detector")

# What to do the Nth time (1-indexed) a given step has failed.
# Index past the end of this list repeats the last entry.
ESCALATION_LADDER = ["retry", "self_heal", "rollback", "replan", "abandon"]


class FailureDetector:
    def classify(self, state: ResultState, attempt_number: int = 1) -> Dict:
        """Returns {"is_failure", "is_partial", "action", "attempt_number"}.
        `action` is the escalation ladder rung for this attempt -
        core/orchestrator.py is expected to call the matching module
        (self_healing_engine, rollback, replanner) itself; this
        method only names which one."""
        is_failure = state == ResultState.VERIFIED_FAILURE
        is_partial = state == ResultState.PARTIAL_SUCCESS
        is_unknown = state == ResultState.UNKNOWN

        if not (is_failure or is_partial or is_unknown):
            return {"is_failure": False, "is_partial": False, "action": "none", "attempt_number": attempt_number}

        rung = ESCALATION_LADDER[min(attempt_number - 1, len(ESCALATION_LADDER) - 1)]

        # UNKNOWN and PARTIAL are treated one rung more leniently than
        # a confirmed failure - no point rolling back a step we're not
        # even sure failed.
        if (is_unknown or is_partial) and rung in ("rollback", "replan"):
            rung = "self_heal"

        logger.info(f"Step classified as {state.name}, attempt {attempt_number} -> action '{rung}'")
        return {"is_failure": is_failure, "is_partial": is_partial, "action": rung, "attempt_number": attempt_number}


_instance: Optional[FailureDetector] = None


def get_failure_detector() -> FailureDetector:
    global _instance
    if _instance is None:
        _instance = FailureDetector()
    return _instance
