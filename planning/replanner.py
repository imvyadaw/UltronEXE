"""
Replanner (Phase 30 - Planning)
==================================
cognitive_core/autonomous_executor.py already retries a failed
sub-goal by re-decomposing it with the self_critique_agent's
suggested_fix folded in (see its module docstring) - but that logic
is private to that one executor and only fires inside its own
run_goal() loop. core/orchestrator.py needs the same "failed step ->
new plan for just that step" behavior available as a standalone call,
so it can invoke it after verification/failure_detector.py flags a
failure, regardless of which loop produced the original plan.

Deliberately thin: this does not re-implement decomposition. It
reuses intelligence/goal_manager/goal_decomposer.py to regenerate
steps, and folds in a `hint` (typically from
intelligence/self_healing/strategy_generator.py or a self-critique
result) so the new attempt isn't identical to the one that just
failed.
"""

from typing import List, Optional

from core.logger import get_logger
from intelligence.goal_manager.goal_decomposer import get_goal_decomposer

logger = get_logger("ultron.planning.replanner")


class Replanner:
    def __init__(self):
        self._decomposer = get_goal_decomposer()

    def replan_step(self, original_title: str, failure_reason: str, hint: Optional[str] = None) -> List[str]:
        """Returns a fresh list of tool-call-style step descriptions
        for the same intent, informed by why the last attempt failed.
        Never raises - on any internal error, falls back to
        re-decomposing the plain original_title unchanged, so a
        replan attempt degrades to "try again" rather than blocking
        the caller's loop."""
        annotated_description = (
            f"Previous attempt failed: {failure_reason}."
            + (f" Suggested fix: {hint}." if hint else "")
            + " Produce an alternative approach, not a repeat of the same steps."
        )
        try:
            return self._decomposer.decompose(original_title, annotated_description)
        except Exception as e:
            logger.warning(f"Replan failed for '{original_title}', falling back to plain decompose: {e}")
            try:
                return self._decomposer.decompose(original_title)
            except Exception as e2:
                logger.error(f"Fallback decompose also failed for '{original_title}': {e2}")
                return []

    def should_replan(self, attempt_count: int, max_attempts: int = 2) -> bool:
        return attempt_count < max_attempts


_instance: Optional[Replanner] = None


def get_replanner() -> Replanner:
    global _instance
    if _instance is None:
        _instance = Replanner()
    return _instance
