"""
Goal Manager (Phase 21 - Unified Core Architecture)
====================================================
Thin core/-level facade over intelligence/goal_manager/goal_manager.py
(Phase 19.3), which already owns the real lifecycle (goal_store,
goal_decomposer, progress_tracker, pause_resume, recovery_manager) -
this module does not reimplement any of that. It exists so the Phase 21
modules (unified_context, action_pipeline, autonomous_engine,
consciousness) can all `from core.goal_manager import get_goal_manager`
without reaching into intelligence/ directly, and so goal lifecycle
changes are announced on core.event_bus, which the intelligence-layer
module doesn't do on its own.

If intelligence.goal_manager isn't importable for some reason (partial
checkout, missing dependency), this falls back to a minimal in-memory
goal list so callers still get a working active_goal()/create_goal()
instead of an ImportError - degraded, not broken.
"""

import threading
import time
import uuid
from typing import Dict, List, Optional

from core.logger import get_logger

logger = get_logger("ultron.core.goal_manager")


class _FallbackGoalManager:
    """Minimal in-memory stand-in, used only if the Phase 19.3 package
    can't be imported."""

    def __init__(self):
        self._goals: Dict[str, Dict] = {}
        self._active_id: Optional[str] = None

    def create_goal(
        self,
        title: str,
        description: str = "",
        priority: str = "normal",
        deadline: Optional[float] = None,
        auto_decompose: bool = True,
        expected_intents: Optional[List[str]] = None,
    ) -> Dict:
        goal_id = str(uuid.uuid4())
        goal = {
            "id": goal_id,
            "title": title,
            "description": description,
            "priority": priority,
            "deadline": deadline,
            "status": "active",
            "steps": [],
            "created_at": time.time(),
        }
        self._goals[goal_id] = goal
        self._active_id = self._active_id or goal_id
        return goal

    def get_goal(self, goal_id: str) -> Optional[Dict]:
        return self._goals.get(goal_id)

    def list_goals(self, status: Optional[str] = None) -> List[Dict]:
        goals = list(self._goals.values())
        return [g for g in goals if g["status"] == status] if status else goals

    def complete_goal(self, goal_id: str) -> Optional[Dict]:
        goal = self._goals.get(goal_id)
        if goal:
            goal["status"] = "completed"
            if self._active_id == goal_id:
                self._active_id = None
        return goal


class CoreGoalManager:
    """Process-wide facade. Use get_goal_manager()."""

    def __init__(self):
        self._impl = self._load_impl()

    def _load_impl(self):
        try:
            from intelligence.goal_manager.goal_manager import get_goal_manager as get_real

            return get_real()
        except Exception as exc:
            logger.warning(f"intelligence.goal_manager unavailable, using fallback: {exc}")
            return _FallbackGoalManager()

    def create_goal(self, title: str, **kwargs) -> Dict:
        goal = self._impl.create_goal(title, **kwargs)
        self._emit("goal.created", goal_id=goal.get("id"), title=title)
        return goal

    def complete_goal(self, goal_id: str) -> Optional[Dict]:
        """intelligence.goal_manager.GoalManager (Phase 19.3) has no
        complete_goal of its own - goal completion there is driven by
        progress_tracker as steps finish, not a direct status flip. Reach
        its underlying goal_store when available (same object the real
        GoalManager already owns as self._store) so 'completed' is the
        one path callers use regardless of which impl is backing this
        facade; the fallback impl has its own complete_goal directly."""
        if hasattr(self._impl, "complete_goal"):
            goal = self._impl.complete_goal(goal_id)
        elif hasattr(self._impl, "_store") and hasattr(self._impl._store, "update_goal"):
            self._impl._store.update_goal(goal_id, status="completed")
            goal = self.get_goal(goal_id)
        else:
            logger.warning(f"goal_manager: no way to mark goal {goal_id} completed on this impl")
            goal = self.get_goal(goal_id)
        if goal:
            self._emit("goal.completed", goal_id=goal_id, title=goal.get("title"))
        return goal

    def get_goal(self, goal_id: str) -> Optional[Dict]:
        return self._impl.get_goal(goal_id)

    def list_goals(self, status: Optional[str] = None) -> List[Dict]:
        return self._impl.list_goals(status=status)

    def active_goal(self) -> Optional[Dict]:
        """Most recently created goal still in 'active' status, or None.
        Re-fetches through get_goal() so the result always includes
        'steps' - list_goals() alone returns bare rows on the real
        (Phase 19.3) impl, no steps/progress attached."""
        active = self.list_goals(status="active")
        if not active:
            return None
        return self.get_goal(active[-1]["id"])

    def _emit(self, event_name: str, **payload) -> None:
        try:
            from core.event_bus import get_event_bus

            get_event_bus().emit(event_name, **payload)
        except Exception:
            from core.error_trace import log_swallowed as _lsw

            _lsw("core.goal_manager._emit")


_manager: Optional[CoreGoalManager] = None
_lock = threading.Lock()


def get_goal_manager() -> CoreGoalManager:
    global _manager
    if _manager is None:
        with _lock:
            if _manager is None:
                _manager = CoreGoalManager()
    return _manager
