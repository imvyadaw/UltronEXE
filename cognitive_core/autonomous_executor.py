"""
Autonomous executor
====================
Ties the rest of COGNITIVE_CORE together into one bounded loop:

    goal_planner.plan_goal(goal)              -> sub-goals
    for each sub-goal:
        task_decomposer.decompose(sub-goal)    -> tool-call steps
        core.workflow_engine.run_ad_hoc(steps) -> execution report
                                                   (retries already
                                                   handled inside via
                                                   core.error_handler -
                                                   not reimplemented here)
        self_critique_agent.critique(...)      -> satisfied / reason / fix
        not satisfied and budget left?         -> re-decompose *that*
                                                   sub-goal with the
                                                   critique's suggested_fix
                                                   folded in, try again
        else                                   -> record and move on

Every actual tool call still goes through core.executor.execute_tool
via core.workflow_engine - this file adds judgement about *when* to
retry and *when to stop*, it never gains any capability the tool
schema didn't already expose.

Bounded on purpose - "autonomous" here means "doesn't need a human to
approve each step", not "can run forever":
    MAX_SUBGOAL_ATTEMPTS - retries per sub-goal after a failed critique
    MAX_TOTAL_STEPS      - hard ceiling on tool calls across the whole
                            goal, regardless of how many sub-goals or
                            retries that implies. Once reached, the
                            executor stops issuing new steps and returns
                            everything gathered so far with
                            "stopped_reason": "step_ceiling_reached" -
                            it never silently keeps going past the cap.
"""

from typing import Dict, List, Optional, Tuple

from core.workflow_engine import get_workflow_engine

from cognitive_core.goal_planner import get_goal_planner
from cognitive_core.task_decomposer import get_task_decomposer
from cognitive_core.self_critique_agent import get_self_critique_agent
from cognitive_core.context_bridge import get_context_bridge

MAX_SUBGOAL_ATTEMPTS = 2
MAX_TOTAL_STEPS = 40


class AutonomousExecutor:
    def __init__(self):
        self._goal_planner = get_goal_planner()
        self._decomposer = get_task_decomposer()
        self._critique = get_self_critique_agent()
        self._ctx = get_context_bridge()
        self._workflow_engine = get_workflow_engine()

    def run_goal(self, goal: str, quick: bool = False, stop_on_step_error: bool = False) -> Dict:
        """Runs the full pipeline for `goal` and returns a report:
        {"goal", "satisfied", "subgoal_results": [...], "total_steps_run",
        "stopped_reason": Optional[str]}. Never raises - any internal
        failure degrades to a returned {"error": ...} entry rather than
        propagating, matching every other Ultron execution path.

        quick=True skips the sub-goal layer entirely and just runs
        goal_planner.quick_plan() + one critique pass - the fast path
        for a goal simple enough not to need decomposition (mirrors
        core/planner.py's Planner.plan_and_run(), plus a critique step
        that didn't exist before).
        """
        self._ctx.emit_stage("started", goal=goal, quick=quick)

        if quick:
            result = self._run_quick(goal, stop_on_step_error)
            self._ctx.emit_stage("complete", goal=goal, satisfied=result.get("satisfied"))
            return result

        plan = self._goal_planner.plan_goal(goal)
        if "error" in plan:
            self._ctx.emit_stage("complete", goal=goal, satisfied=False, error=plan["error"])
            return {"goal": goal, "satisfied": False, "error": plan["error"], "subgoal_results": []}

        subgoal_results: List[Dict] = []
        total_steps_run = 0
        stopped_reason: Optional[str] = None
        overall_satisfied = True

        for idx, sg in enumerate(plan["subgoals"]):
            if total_steps_run >= MAX_TOTAL_STEPS:
                stopped_reason = "step_ceiling_reached"
                break

            title = sg.get("title", "")
            self._ctx.emit_stage("subgoal", index=idx, title=title)

            attempt_result, steps_run = self._run_subgoal_with_retries(
                title, budget_remaining=MAX_TOTAL_STEPS - total_steps_run, stop_on_step_error=stop_on_step_error
            )
            total_steps_run += steps_run
            subgoal_results.append({"index": idx, "title": title, **attempt_result})

            if not attempt_result.get("satisfied", False):
                overall_satisfied = False

        summary = f"{sum(1 for r in subgoal_results if r.get('satisfied'))}/{len(subgoal_results)} sub-goals satisfied"
        self._ctx.remember_outcome(goal, summary, overall_satisfied)
        self._ctx.emit_stage("complete", goal=goal, satisfied=overall_satisfied, stopped_reason=stopped_reason)

        return {
            "goal": goal,
            "satisfied": overall_satisfied,
            "subgoal_results": subgoal_results,
            "total_steps_run": total_steps_run,
            "stopped_reason": stopped_reason,
        }

    # -- internals -----------------------------------------------------------
    def _run_subgoal_with_retries(
        self, title: str, budget_remaining: int, stop_on_step_error: bool
    ) -> Tuple[Dict, int]:
        feedback: Optional[str] = None
        steps_run_total = 0
        last_critique: Dict = {}

        for attempt in range(1, MAX_SUBGOAL_ATTEMPTS + 1):
            decomposed = (
                self._decomposer.decompose(title)
                if feedback is None
                else self._decomposer.decompose(f"{title}\n\nPreviously tried and failed because: {feedback}")
            )
            if "error" in decomposed:
                return {
                    "satisfied": False,
                    "attempts": attempt,
                    "error": decomposed["error"],
                    "critique": last_critique,
                }, steps_run_total

            steps = decomposed["steps"][:budget_remaining]
            if not steps:
                return {
                    "satisfied": False,
                    "attempts": attempt,
                    "error": "no steps generated",
                    "critique": last_critique,
                }, steps_run_total

            report = self._workflow_engine.run_ad_hoc(steps, stop_on_error=stop_on_step_error)
            steps_run_total += len(report.get("steps", []))
            budget_remaining -= len(report.get("steps", []))

            last_critique = self._critique.critique(title, report)
            self._ctx.emit_stage("critique", subgoal=title, attempt=attempt, satisfied=last_critique.get("satisfied"))

            if last_critique.get("satisfied"):
                return {
                    "satisfied": True,
                    "attempts": attempt,
                    "report": report,
                    "critique": last_critique,
                }, steps_run_total

            feedback = last_critique.get("suggested_fix") or last_critique.get("reason")
            if budget_remaining <= 0:
                break

        return {
            "satisfied": False,
            "attempts": MAX_SUBGOAL_ATTEMPTS,
            "report": report,
            "critique": last_critique,
        }, steps_run_total

    def _run_quick(self, goal: str, stop_on_step_error: bool) -> Dict:
        plan = self._goal_planner.quick_plan(goal)
        if "error" in plan:
            return {"goal": goal, "satisfied": False, "error": plan["error"]}

        steps = plan.get("steps", [])[:MAX_TOTAL_STEPS]
        report = self._workflow_engine.run_ad_hoc(steps, stop_on_error=stop_on_step_error)
        critique = self._critique.critique(goal, report)
        self._ctx.remember_outcome(goal, critique.get("reason", ""), critique.get("satisfied", False))
        return {
            "goal": goal,
            "satisfied": critique.get("satisfied", False),
            "report": report,
            "critique": critique,
            "total_steps_run": len(report.get("steps", [])),
        }


_executor: Optional[AutonomousExecutor] = None


def get_autonomous_executor() -> AutonomousExecutor:
    global _executor
    if _executor is None:
        _executor = AutonomousExecutor()
    return _executor
