"""
Goal Bridge (Phase 20.4 - Intelligence Bridge)
==================================================
Thin, defensive bridge onto ULTRON's goal-planning/execution subsystem
- either a later intelligence/-level module, or (falling back) Phase
17.2's COGNITIVE_CORE goal_planner.py / autonomous_executor.py, whose
plan -> execute -> critique -> replan loop this codebase already has.
See _bridge_utils.py for the resolve-by-name/keyword + degrade-to-no-op
approach every bridge in this package shares.

Usage:
    from intelligence_bridge.goal_bridge import get_goal_bridge

    gb = get_goal_bridge()
    if gb.is_available():
        plan = gb.plan("book a table for two tonight")

Purely additive - every method here is a best-effort call that returns
None on failure instead of raising.
"""

from typing import Any, Dict, Optional

from intelligence_bridge._bridge_utils import (
    first_success,
    resolve_module,
    resolve_singleton,
    safe_call,
    logger,
)

_CANDIDATE_MODULES = (
    "intelligence.goal.goal_engine",
    "intelligence.goal",
    "intelligence.goal_engine",
    "intelligence.goal_management",
    "cognitive_core.goal_planner",
    "cognitive_core.autonomous_executor",
)
_KEYWORDS = ("goal",)
_GETTER_NAMES = ("get_goal_manager", "get_goal_engine", "get_goal_planner", "get_autonomous_executor")
_CLASS_NAMES = ("GoalManager", "GoalEngine", "GoalPlanner", "AutonomousExecutor")


class GoalBridge:
    """Bridges to ULTRON's goal planning/execution subsystem."""

    def __init__(self):
        self._module = resolve_module(_CANDIDATE_MODULES, _KEYWORDS)
        self._instance = resolve_singleton(self._module, _GETTER_NAMES, _CLASS_NAMES)
        if self._instance is not None:
            logger.info("[goal_bridge] connected to %s", getattr(self._module, "__name__", "?"))
        else:
            logger.info("[goal_bridge] underlying module not found - running in degraded/no-op mode")

    def is_available(self) -> bool:
        return self._instance is not None

    def status(self) -> Dict[str, Any]:
        return {
            "bridge": "goal",
            "available": self.is_available(),
            "source_module": getattr(self._module, "__name__", None),
        }

    def plan(self, goal_text: str, *args, **kwargs) -> Optional[Any]:
        """Best-effort plan/breakdown for `goal_text`. Phase 19.3's
        GoalManager.create_goal(title, ...) doesn't take a `context`
        kwarg the way the generic candidates below assume, so this
        drops it before trying "create_goal" specifically."""
        result = first_success(
            self._instance,
            ("plan", "plan_goal", "create_plan", "decompose", "breakdown_goal"),
            goal_text,
            *args,
            **kwargs,
        )
        if result is not None:
            return result
        return safe_call(self._instance, "create_goal", goal_text)

    def get_status(self, goal_id: Any, *args, **kwargs) -> Optional[Any]:
        """Best-effort progress/status lookup for a previously-planned goal."""
        return first_success(
            self._instance,
            ("get_status", "status", "get_progress", "get_goal_status", "get_goal"),
            goal_id,
            *args,
            **kwargs,
        )

    def execute(self, goal_text: str, *args, **kwargs) -> Optional[Any]:
        """Best-effort hand-off to whatever executes goals end-to-end."""
        return first_success(
            self._instance,
            ("execute", "run", "execute_goal", "run_goal"),
            goal_text,
            *args,
            **kwargs,
        )

    def call(self, method_name: str, *args, **kwargs) -> Optional[Any]:
        """Generic passthrough for anything not covered above."""
        return safe_call(self._instance, method_name, *args, **kwargs)


_bridge_instance: Optional[GoalBridge] = None


def get_goal_bridge() -> GoalBridge:
    """Process-wide GoalBridge singleton."""
    global _bridge_instance
    if _bridge_instance is None:
        _bridge_instance = GoalBridge()
    return _bridge_instance
