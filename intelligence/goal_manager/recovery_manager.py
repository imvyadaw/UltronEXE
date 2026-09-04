"""
Recovery Manager (Phase 19.3 - Goal Manager)
================================================
Finds goals that look abandoned - status 'active', but no
goal_events activity (step progress, pause, etc.) for longer than a
threshold - and offers a concrete next action to get them moving
again, rather than quietly forgetting about them. Deliberately
'paused' goals (pause_resume.py) are never flagged as stalled; that
distinction is the whole reason pausing writes its own event.

This module never abandons or edits a goal on its own - check_stalled()
only reports, and attempt_recovery() only suggests + logs. Whether a
goal actually gets abandoned is a caller/user decision, made via
goal_store.update_goal(goal_id, status="abandoned").
"""

import threading
import time
from typing import Dict, List, Optional

from core.logger import get_logger
from intelligence.goal_manager.goal_store import get_goal_store

logger = get_logger("ultron.recovery_manager")

SECONDS_PER_DAY = 86400

_instance: Optional["RecoveryManager"] = None
_instance_lock = threading.Lock()


class RecoveryManager:
    """Stall detection + recovery suggestions for active goals that
    have gone quiet."""

    def __init__(self):
        self._store = get_goal_store()

    def check_stalled(self, threshold_days: float = 7.0) -> List[Dict]:
        """Every 'active' goal whose most recent goal_events row (or,
        if it somehow has none, its created_at) is older than
        threshold_days. Each result also gets a 'stalled' event logged
        so repeated checks don't silently do nothing."""
        cutoff = time.time() - threshold_days * SECONDS_PER_DAY
        stalled = []
        for goal in self._store.list_goals(status="active"):
            last_activity = self._store.last_event_time(goal["id"]) or goal["created_at"]
            if last_activity < cutoff:
                idle_days = round((time.time() - last_activity) / SECONDS_PER_DAY, 1)
                stalled.append({**goal, "idle_days": idle_days})
                self._store.log_event(goal["id"], "stalled_detected", {"idle_days": idle_days})
                logger.info(f"goal {goal['id']} looks stalled - idle {idle_days} days")
        return stalled

    def attempt_recovery(self, goal_id: str) -> Dict:
        """Suggest the next concrete action on a stalled goal: its
        earliest non-done, non-skipped step. Logs a
        'recovery_attempted' event either way. Does not change any
        step or goal status - it's advisory, the same shape a caller
        would use to nudge the user or re-surface the goal in a UI."""
        goal = self._store.get_goal(goal_id)
        if goal.get("error"):
            return goal

        steps = self._store.list_steps(goal_id)
        next_step = next((s for s in steps if s["status"] in ("pending", "in_progress")), None)

        if next_step:
            suggestion = {
                "goal_id": goal_id,
                "suggested_next_step": next_step,
                "message": f"Pick back up on '{goal['title']}' with: {next_step['description']}",
            }
        elif not steps:
            suggestion = {
                "goal_id": goal_id,
                "suggested_next_step": None,
                "message": f"'{goal['title']}' has no steps yet - decompose it to get a starting point.",
            }
        else:
            suggestion = {
                "goal_id": goal_id,
                "suggested_next_step": None,
                "message": f"All steps on '{goal['title']}' are already done/skipped - it may just need to be marked completed.",
            }

        self._store.log_event(goal_id, "recovery_attempted", suggestion)
        return suggestion

    def recovery_report(self, threshold_days: float = 7.0) -> List[Dict]:
        """Convenience: check_stalled() + attempt_recovery() for each
        result, in one call."""
        return [self.attempt_recovery(g["id"]) for g in self.check_stalled(threshold_days)]


def get_recovery_manager() -> RecoveryManager:
    """Process-wide RecoveryManager singleton."""
    global _instance
    if _instance is None:
        with _instance_lock:
            if _instance is None:
                _instance = RecoveryManager()
    return _instance
