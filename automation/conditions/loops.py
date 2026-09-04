"""Loops
=====
Repeat a tool call: a fixed number of times, while a condition holds
(via if_conditions.ConditionEvaluator), or once per item in a list
(passing each item in as an extra argument). Used by RPA scripts and
workflows for repetition without hand-written code.
"""

import json
import time
from typing import Any, Dict, List

from automation.conditions.if_conditions import ConditionEvaluator


class LoopRunner:
    """Repeat a tool call under different repetition strategies."""

    def __init__(self):
        self._conditions = ConditionEvaluator()

    def repeat(
        self, tool_name: str, arguments: Dict, times: int, delay_seconds: float = 0.0, stop_on_error: bool = True
    ) -> Dict:
        """Run tool_name(arguments) `times` times in a row."""
        from ai.tool_runtime import execute_tool_call as execute_tool

        results = []
        for i in range(times):
            raw = execute_tool(tool_name, arguments)
            parsed = json.loads(raw)
            results.append({"iteration": i + 1, "result": parsed})
            if stop_on_error and "error" in parsed:
                return {"success": False, "completed": i + 1, "total": times, "results": results}
            if delay_seconds and i < times - 1:
                time.sleep(delay_seconds)
        return {"success": True, "completed": times, "total": times, "results": results}

    def while_condition(
        self, condition: Dict, tool_name: str, arguments: Dict, max_iterations: int = 100, delay_seconds: float = 1.0
    ) -> Dict:
        """Run tool_name(arguments) repeatedly while `condition` evaluates true,
        checked before each iteration. Capped by max_iterations as a safety net."""
        from ai.tool_runtime import execute_tool_call as execute_tool

        results = []
        iteration = 0
        while iteration < max_iterations:
            check = self._conditions.evaluate(condition)
            if "error" in check:
                return check
            if not check["result"]:
                break
            raw = execute_tool(tool_name, arguments)
            results.append({"iteration": iteration + 1, "result": json.loads(raw)})
            iteration += 1
            if iteration < max_iterations:
                time.sleep(delay_seconds)
        return {
            "success": True,
            "iterations_run": iteration,
            "stopped_reason": "max_iterations" if iteration >= max_iterations else "condition_false",
            "results": results,
        }

    def for_each(
        self,
        tool_name: str,
        base_arguments: Dict,
        items: List[Any],
        item_arg_name: str,
        delay_seconds: float = 0.0,
        stop_on_error: bool = False,
    ) -> Dict:
        """Run tool_name once per item in `items`, injecting each item under
        item_arg_name into base_arguments (e.g. item_arg_name='url' to open a
        list of URLs one by one)."""
        from ai.tool_runtime import execute_tool_call as execute_tool

        results = []
        for i, item in enumerate(items):
            args = dict(base_arguments)
            args[item_arg_name] = item
            raw = execute_tool(tool_name, args)
            parsed = json.loads(raw)
            results.append({"item": item, "result": parsed})
            if stop_on_error and "error" in parsed:
                return {"success": False, "completed": i + 1, "total": len(items), "results": results}
            if delay_seconds and i < len(items) - 1:
                time.sleep(delay_seconds)
        return {"success": True, "completed": len(items), "total": len(items), "results": results}
