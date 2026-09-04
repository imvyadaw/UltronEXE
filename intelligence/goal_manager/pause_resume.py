"""
Pause / Resume (Phase 19.3 - Goal Manager)
==============================================
Handles the 'active' <-> 'paused' side of a goal's lifecycle
(completed/abandoned are set directly through goal_store/
progress_tracker/recovery_manager). Every pause/resume is written
through goal_store.update_goal() plus a matching goal_events row, so
recovery_manager.py can tell a genuinely stalled active goal apart
from one the user deliberately parked.
"""

import threading
import time
from typing import Dict, List, Optional

from core.logger import get_logger
from intelligence.goal_manager.goal_store import get_goal_store

logger = get_logger("ultron.pause_resume")

_instance: Optional["PauseResumeManager"] = None
_instance_lock = threading.Lock()


class PauseResumeManager:
    """Pause/resume a goal, and answer 'is this goal paused / which
    goals are currently paused' without callers touching goal_store
    directly."""

    def __init__(self):
        self._store = get_goal_store()

    def pause_goal(self, goal_id: str, reason: Optional[str] = None) -> Dict:
        goal = self._store.get_goal(goal_id)
        if goal.get("error"):
            return goal
        if goal["status"] != "active":
            return {"error": f"goal {goal_id} is '{goal['status']}', can only pause an 'active' goal"}
        updated = self._store.update_goal(goal_id, status="paused")
        self._store.log_event(goal_id, "paused", {"reason": reason, "paused_at": time.time()})
        logger.info(f"goal {goal_id} paused" + (f" ({reason})" if reason else ""))
        return updated

    def resume_goal(self, goal_id: str) -> Dict:
        goal = self._store.get_goal(goal_id)
        if goal.get("error"):
            return goal
        if goal["status"] != "paused":
            return {"error": f"goal {goal_id} is '{goal['status']}', can only resume a 'paused' goal"}
        updated = self._store.update_goal(goal_id, status="active")
        self._store.log_event(goal_id, "resumed", {"resumed_at": time.time()})
        logger.info(f"goal {goal_id} resumed")
        return updated

    def is_paused(self, goal_id: str) -> bool:
        goal = self._store.get_goal(goal_id)
        return goal.get("status") == "paused"

    def list_paused_goals(self) -> List[Dict]:
        return self._store.list_goals(status="paused")


def get_pause_resume_manager() -> PauseResumeManager:
    """Process-wide PauseResumeManager singleton."""
    global _instance
    if _instance is None:
        with _instance_lock:
            if _instance is None:
                _instance = PauseResumeManager()
    return _instance
