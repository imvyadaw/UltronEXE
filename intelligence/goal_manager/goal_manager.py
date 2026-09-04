"""
Goal Manager (Phase 19.3 - Goal Manager)
============================================
Single entry point for the goal_manager/ package: create a goal,
optionally auto-decompose it into steps, advance/complete steps,
pause/resume it, and check on/recover stalled goals - all through
one object instead of five.

Relationship to intelligence.intent_prediction.goal_predictor
(Phase 19.2): that module is a lightweight "does recent *intent*
activity match a caller-registered set of expected intents"
scorer - it doesn't know about steps, progress, pausing, or
staleness. This module is the fuller lifecycle manager: real goals
with ordered steps, completion tracking, pause/resume, and stall
recovery. create_goal(..., expected_intents=[...]) can optionally
register a matching entry in the Phase 19.2 goal_predictor and
store its id as linked_intent_goal_id, so a goal created here can
still be picked up by intent-based inference if a caller wants that;
this is opt-in and entirely skippable.

Storage: database/goals.db (via goal_store.py) - this module owns no
storage of its own.
"""

import threading
from typing import Dict, List, Optional

from core.logger import get_logger
from intelligence.goal_manager.goal_store import get_goal_store
from intelligence.goal_manager.goal_decomposer import get_goal_decomposer
from intelligence.goal_manager.progress_tracker import get_progress_tracker
from intelligence.goal_manager.pause_resume import get_pause_resume_manager
from intelligence.goal_manager.recovery_manager import get_recovery_manager

logger = get_logger("ultron.goal_manager")

_instance: Optional["GoalManager"] = None
_instance_lock = threading.Lock()


class GoalManager:
    """Orchestrates goal_store / goal_decomposer / progress_tracker /
    pause_resume / recovery_manager into one create/advance/pause/
    resume/recover API."""

    def __init__(self):
        self._store = get_goal_store()
        self._decomposer = get_goal_decomposer()
        self._progress = get_progress_tracker()
        self._pause_resume = get_pause_resume_manager()
        self._recovery = get_recovery_manager()

    # -- lifecycle --------------------------------------------------------------
    def create_goal(
        self,
        title: str,
        description: str = "",
        priority: str = "normal",
        deadline: Optional[float] = None,
        auto_decompose: bool = True,
        expected_intents: Optional[List[str]] = None,
    ) -> Dict:
        """Create a goal and, by default, immediately decompose it into
        steps. Pass expected_intents to also register this goal with
        Phase 19.2's intent-based goal_predictor (best-effort - if that
        module isn't importable for some reason, the goal is still
        created here, just without the link)."""
        linked_intent_goal_id = None
        if expected_intents:
            try:
                from intelligence.intent_prediction.goal_predictor import get_goal_predictor

                intent_goal = get_goal_predictor().register_goal(title, expected_intents)
                linked_intent_goal_id = intent_goal.get("id")
            except Exception as exc:
                logger.warning(f"could not register intent-goal link for '{title}': {exc}")

        goal = self._store.create_goal(
            title=title,
            description=description,
            priority=priority,
            deadline=deadline,
            linked_intent_goal_id=linked_intent_goal_id,
        )
        if goal.get("error"):
            return goal

        if auto_decompose:
            self._decomposer.decompose_and_create(goal["id"])

        return self.get_goal(goal["id"])

    def get_goal(self, goal_id: str) -> Dict:
        """Full detail view: the goal row, its steps, and its progress."""
        goal = self._store.get_goal(goal_id)
        if goal.get("error"):
            return goal
        return {
            **goal,
            "steps": self._store.list_steps(goal_id),
            "progress": self._progress.compute_progress(goal_id),
        }

    def list_goals(self, status: Optional[str] = None) -> List[Dict]:
        return self._store.list_goals(status=status)

    def delete_goal(self, goal_id: str) -> Dict:
        return self._store.delete_goal(goal_id)

    # -- steps / progress -------------------------------------------------------
    def add_step(self, goal_id: str, description: str) -> Dict:
        return self._store.add_step(goal_id, description)

    def advance_step(self, step_id: str) -> Dict:
        """Mark a step done and auto-complete the parent goal if that
        was the last one left."""
        return self._progress.mark_step_complete(step_id)

    def skip_step(self, step_id: str) -> Dict:
        return self._progress.mark_step_skipped(step_id)

    def get_progress(self, goal_id: str) -> Dict:
        return self._progress.compute_progress(goal_id)

    # -- pause / resume -----------------------------------------------------------
    def pause_goal(self, goal_id: str, reason: Optional[str] = None) -> Dict:
        return self._pause_resume.pause_goal(goal_id, reason=reason)

    def resume_goal(self, goal_id: str) -> Dict:
        return self._pause_resume.resume_goal(goal_id)

    def list_paused_goals(self) -> List[Dict]:
        return self._pause_resume.list_paused_goals()

    # -- recovery -------------------------------------------------------------------
    def check_stalled_goals(self, threshold_days: float = 7.0) -> List[Dict]:
        return self._recovery.check_stalled(threshold_days)

    def recover_goal(self, goal_id: str) -> Dict:
        return self._recovery.attempt_recovery(goal_id)

    def recovery_report(self, threshold_days: float = 7.0) -> List[Dict]:
        return self._recovery.recovery_report(threshold_days)

    def abandon_goal(self, goal_id: str, reason: Optional[str] = None) -> Dict:
        """Explicit give-up: distinct from stalling out silently. Always
        a deliberate call - recovery_manager never does this on its own."""
        updated = self._store.update_goal(goal_id, status="abandoned")
        if not updated.get("error"):
            self._store.log_event(goal_id, "abandoned", {"reason": reason})
            logger.info(f"goal {goal_id} abandoned" + (f" ({reason})" if reason else ""))
        return updated


def get_goal_manager() -> GoalManager:
    """Process-wide GoalManager singleton."""
    global _instance
    if _instance is None:
        with _instance_lock:
            if _instance is None:
                _instance = GoalManager()
    return _instance
