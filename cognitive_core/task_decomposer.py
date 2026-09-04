"""
Task decomposer
================
Turns one sub-goal (from goal_planner.py) into concrete tool-call steps
shaped exactly like core/workflow_engine.py already expects them -
{"tool", "arguments", "label", "run_if"?, "max_retries"?} - by reusing
ai.planning.Planner.make_plan() for the actual tool-schema-validated
decomposition (same tool names, same JSON contract core/planner.py
already relies on). This module's own job is everything around that
one call: labelling steps for readable reports, and - when decomposing
a whole multi-sub-goal plan at once via decompose_all() - chaining
sub-goals together with run_if guards so a later sub-goal doesn't fire
against a broken result from an earlier one.
"""

from typing import Dict, List, Optional

from ai.planning import Planner as ToolPlanGenerator


class TaskDecomposer:
    def __init__(self):
        self._tool_planner = ToolPlanGenerator()

    def decompose(self, subgoal_title: str) -> Dict:
        """One sub-goal -> {"subgoal", "steps"}. `steps` is ready to hand
        to core.workflow_engine.WorkflowEngine.run_ad_hoc() as-is (or
        append to a larger step list - see decompose_all()). Passes
        through ai.planning.Planner's own {"error": ...} shape unchanged
        on failure, so callers only need to check one key either way."""
        plan = self._tool_planner.make_plan(subgoal_title)
        if "error" in plan:
            return plan

        steps = plan.get("steps", [])
        for i, step in enumerate(steps):
            step.setdefault("label", f"{subgoal_title[:50]} (step {i + 1})")
        return {"subgoal": subgoal_title, "steps": steps, "step_count": len(steps)}

    def decompose_all(self, subgoals: List[Dict], chain_on_failure: bool = False) -> Dict:
        """Decomposes every sub-goal (as returned by
        goal_planner.plan_goal()'s "subgoals" list) into one flat,
        numbered step list. Each step also carries "subgoal_index" so
        autonomous_executor / self_critique_agent can attribute a
        result back to the sub-goal that produced it.

        chain_on_failure=True inserts a run_if guard on the first step
        of every sub-goal after the first, requiring the previous
        sub-goal's last step to have succeeded - use this only when
        sub-goals are genuinely sequential-dependent; leave it False
        (default) when sub-goals are independent and should all get a
        chance to run even if an earlier one failed, which is the
        safer default for an autonomous run.
        """
        flat_steps: List[Dict] = []
        per_subgoal: List[Dict] = []
        errors: List[str] = []

        step_number = 0
        last_subgoal_last_step: Optional[int] = None

        for idx, sg in enumerate(subgoals):
            title = sg.get("title", "") if isinstance(sg, dict) else str(sg)
            result = self.decompose(title)
            if "error" in result:
                errors.append(f"subgoal {idx} ('{title}'): {result['error']}")
                per_subgoal.append({"subgoal_index": idx, "title": title, "step_count": 0, "error": result["error"]})
                continue

            steps = result["steps"]
            first_step_of_subgoal = step_number + 1
            for step in steps:
                step_number += 1
                step["subgoal_index"] = idx
                if chain_on_failure and last_subgoal_last_step is not None and step_number == first_step_of_subgoal:
                    step["run_if"] = {"step": last_subgoal_last_step, "path": "success", "equals": True}
                flat_steps.append(step)

            if steps:
                last_subgoal_last_step = step_number
            per_subgoal.append({"subgoal_index": idx, "title": title, "step_count": len(steps)})

        return {
            "steps": flat_steps,
            "step_count": len(flat_steps),
            "per_subgoal": per_subgoal,
            "errors": errors,
        }


_decomposer: Optional[TaskDecomposer] = None


def get_task_decomposer() -> TaskDecomposer:
    global _decomposer
    if _decomposer is None:
        _decomposer = TaskDecomposer()
    return _decomposer
