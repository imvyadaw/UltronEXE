"""
Progress Tracker (Phase 19.3 - Goal Manager)
================================================
Turns a goal's steps (from goal_store.py) into a completion
percentage, and is the single place that marks a step done/updated
and auto-completes the parent goal once every step is done or
skipped. Nothing here decides *what* the steps are (that's
goal_decomposer.py) or whether the goal is paused (pause_resume.py)
- it only tracks and reports how far along a goal's steps are.
"""

import threading
from typing import Dict, Optional

from core.logger import get_logger
from intelligence.goal_manager.goal_store import get_goal_store

logger = get_logger("ultron.progress_tracker")

_instance: Optional["ProgressTracker"] = None
_instance_lock = threading.Lock()


class ProgressTracker:
    """Computes per-goal progress and applies step status changes,
    auto-completing the goal when nothing pending/in_progress remains."""

    def __init__(self):
        self._store = get_goal_store()

    def compute_progress(self, goal_id: str) -> Dict:
        """{"total_steps", "completed_steps", "skipped_steps", "percent"}.
        A goal with no steps yet reports 0% rather than dividing by zero."""
        goal = self._store.get_goal(goal_id)
        if goal.get("error"):
            return goal
        steps = self._store.list_steps(goal_id)
        total = len(steps)
        completed = sum(1 for s in steps if s["status"] == "done")
        skipped = sum(1 for s in steps if s["status"] == "skipped")
        percent = round(100.0 * (completed + skipped) / total, 1) if total else 0.0
        return {
            "goal_id": goal_id,
            "total_steps": total,
            "completed_steps": completed,
            "skipped_steps": skipped,
            "percent": percent,
        }

    def mark_step_status(self, step_id: str, status: str) -> Dict:
        """Update a single step's status, then check whether the parent
        goal is now fully done (every step 'done' or 'skipped', at
        least one step 'done') and auto-complete it if so."""
        updated = self._store.update_step(step_id, status)
        if updated.get("error"):
            return updated

        goal_id = updated["goal_id"]
        steps = self._store.list_steps(goal_id)
        if (
            steps
            and all(s["status"] in ("done", "skipped") for s in steps)
            and any(s["status"] == "done" for s in steps)
        ):
            goal = self._store.get_goal(goal_id)
            if goal.get("status") == "active":
                self._store.update_goal(goal_id, status="completed")
                self._store.log_event(goal_id, "completed", {"reason": "all_steps_done"})
                logger.info(f"goal {goal_id} auto-completed - all steps done")

        return {"step": updated, "progress": self.compute_progress(goal_id)}

    def mark_step_complete(self, step_id: str) -> Dict:
        return self.mark_step_status(step_id, "done")

    def mark_step_skipped(self, step_id: str) -> Dict:
        return self.mark_step_status(step_id, "skipped")


def get_progress_tracker() -> ProgressTracker:
    """Process-wide ProgressTracker singleton."""
    global _instance
    if _instance is None:
        with _instance_lock:
            if _instance is None:
                _instance = ProgressTracker()
    return _instance
