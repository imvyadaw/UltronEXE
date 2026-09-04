"""
Planner
=======
Turns a multi-step goal into a plan (via ai/planning.py's LLM-based
decomposition) and, optionally, runs it step by step through
ai/tool_runtime.py's execute_tool_call() - the same execution path
every other tool call goes through, so results are handled identically
whether a step came from the model's normal tool-calling or from a
generated plan.

Bugfix: this used to import execute_tool directly from core/executor.py,
which only covers the original ~340 built-in tools. Everything added
later (apps_tools/new_skills_tools/browser_tools/admin_tools/phase30_*/
etc., ~450 tools) only lives in ai/tool_runtime.py's merged
_DIRECT_HANDLERS map, so any plan step calling one of those tools would
fail with "Unknown tool" even though the same tool works fine from a
normal chat command. Routing through execute_tool_call fixes that.
"""

import json
from typing import Dict

from ai.planning import Planner as PlanGenerator
from ai.tool_runtime import execute_tool_call as execute_tool


class Planner:
    """Generate and optionally run a multi-step plan for a complex goal."""

    def __init__(self):
        self._generator = PlanGenerator()

    def plan(self, goal: str) -> Dict:
        """Just generate the plan (list of tool-call steps), without running it."""
        return self._generator.make_plan(goal)

    def plan_and_run(self, goal: str, stop_on_error: bool = True) -> Dict:
        """Generate a plan for `goal` and immediately execute each step in order."""
        plan_result = self._generator.make_plan(goal)
        if "error" in plan_result:
            return plan_result

        results = []
        for i, step in enumerate(plan_result["steps"]):
            tool_name = step.get("tool")
            arguments = step.get("arguments", {})
            raw_result = execute_tool(tool_name, arguments)
            parsed = json.loads(raw_result)
            results.append({"step": i + 1, "tool": tool_name, "arguments": arguments, "result": parsed})

            if stop_on_error and "error" in parsed:
                return {
                    "success": False,
                    "goal": goal,
                    "failed_at_step": i + 1,
                    "results": results,
                }

        return {"success": True, "goal": goal, "results": results}
