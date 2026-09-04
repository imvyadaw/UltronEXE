"""
Action Manager (Phase 30 - Execution)
========================================
core/action_pipeline.py's module docstring already explains the
problem it solved: four call sites each separately checking
permissions/logging/confidence before ActionPipeline unified them
into one funnel for a *single* action. This module is the equivalent
unification one level up, for callers that need to run either a
single action or a whole ordered plan (a list of steps, e.g. from
planning/replanner.py or a goal's decomposed steps) through the same
gate - and adds the one thing ActionPipeline still doesn't have:
approval/approval_manager.py's queue-and-wait path for medium/high
risk actions, instead of ActionPipeline's binary
confirmed=True/False (which requires the caller to already know the
answer up front).

execute_plan() is what core/orchestrator.py calls; it does not
re-implement step interpolation/conditionals (that's
core/workflow_engine.py's job) - for a plan that needs those features
it hands off to run_ad_hoc() instead of stepping through
ActionPipeline itself.
"""

from typing import Any, Dict, List, Optional

from core.logger import get_logger
from core.action_pipeline import ActionPipeline
from core.workflow_engine import get_workflow_engine
from approval.approval_manager import get_approval_manager

logger = get_logger("ultron.execution.action_manager")


class ActionManager:
    def __init__(self):
        self._pipeline = ActionPipeline()
        self._workflow_engine = get_workflow_engine()
        self._approval = get_approval_manager()

    def execute_action(
        self,
        action_name: str,
        arguments: Optional[Dict[str, Any]] = None,
        user_id: Optional[str] = None,
        source: str = "user",
    ) -> Dict:
        """Single action, approval-aware. If approval_rules.py says
        this needs a human decision, blocks (via
        approval_manager.wait_for_decision) up to its default timeout
        rather than failing outright - callers that can't afford to
        block should call request_approval() themselves instead."""
        arguments = arguments or {}
        decision = self._approval.request(action_name, arguments, source=source)

        if not decision.allowed:
            final_status = self._approval.wait_for_decision(decision.action_id)
            if final_status != "approved":
                return {
                    "success": False,
                    "action": action_name,
                    "error": f"not approved (status={final_status})",
                    "risk_level": decision.risk_level,
                }

        return self._pipeline.run(action_name, arguments, user_id=user_id, source=source, confirmed=True)

    def request_approval_only(self, action_name: str, arguments: Optional[Dict[str, Any]] = None, source: str = "user"):
        """Non-blocking variant for autonomy/task_loop.py: returns the
        ApprovalDecision immediately so the loop can move on to other
        work while this one waits, instead of stalling the whole run
        on wait_for_decision()."""
        return self._approval.request(action_name, arguments or {}, source=source)

    def execute_plan(self, steps: List[Dict], stop_on_error: bool = True, delay_between_steps: float = 0.3) -> Dict:
        """Multi-step plan. Each step is the same dict shape
        core/workflow_engine.py already expects
        ({"tool", "arguments", "run_if"?, "max_retries"?, "label"?}).
        Approval is not re-checked per-step here (workflow_engine has
        no hook for it) - callers running plans containing
        medium/high-risk steps should pre-filter with
        request_approval_only() per step, or run those specific steps
        through execute_action() instead of bundling them into the
        ad-hoc workflow."""
        return self._workflow_engine.run_ad_hoc(
            steps, stop_on_error=stop_on_error, delay_between_steps=delay_between_steps
        )


_instance: Optional[ActionManager] = None


def get_action_manager() -> ActionManager:
    global _instance
    if _instance is None:
        _instance = ActionManager()
    return _instance
