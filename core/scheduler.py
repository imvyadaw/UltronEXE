"""
Scheduler
=========
Ultron-level task scheduling: "remind me in 10 minutes", "check the
weather every morning at 9am". Owns *what* fires (a tool name +
arguments, run through ai/tool_runtime.py's execute_tool_call - the
same fully-wired dispatch every normal chat tool call goes through)
while the low-level timing is handled by
automation/scheduler/task_scheduler.py.

Bugfix: this used to call core.executor.execute_tool directly, which
only knows the original ~340 built-in tools. Anything added later
(apps/browser/admin/phase30/etc., ~450 tools) only lives in
ai/tool_runtime.py's merged handler map, so a scheduled/recurring task
using one of those tools would silently fail with "Unknown tool" at
fire time. Routing through execute_tool_call fixes that.
"""

from datetime import datetime, timedelta
from typing import Dict

from automation.scheduler.task_scheduler import get_scheduler
from ai.tool_runtime import execute_tool_call as execute_tool


class Scheduler:
    """Schedule a Ultron tool call to run later, once or repeatedly."""

    def __init__(self):
        self._backend = get_scheduler()
        self._task_descriptions: Dict[str, Dict] = {}

    def _make_callback(self, tool_name: str, arguments: Dict):
        def callback():
            result = execute_tool(tool_name, arguments)
            print(f"[Scheduler] Ran '{tool_name}' -> {result}")

        return callback

    def schedule_in(self, seconds: float, tool_name: str, arguments: Dict = None) -> Dict:
        """Run a tool once, after `seconds` from now (e.g. 'remind me in 10 minutes')."""
        arguments = arguments or {}
        callback = self._make_callback(tool_name, arguments)
        task_id = self._backend.run_after(seconds, callback)
        self._task_descriptions[task_id] = {
            "tool": tool_name,
            "arguments": arguments,
            "runs_at": (datetime.now() + timedelta(seconds=seconds)).isoformat(),
            "recurring": False,
        }
        return {"success": True, "task_id": task_id, **self._task_descriptions[task_id]}

    def schedule_at(self, when_iso: str, tool_name: str, arguments: Dict = None) -> Dict:
        """Run a tool once, at a specific ISO-format datetime."""
        arguments = arguments or {}
        try:
            when = datetime.fromisoformat(when_iso)
        except ValueError:
            return {"error": f"Invalid ISO datetime: {when_iso}"}
        callback = self._make_callback(tool_name, arguments)
        task_id = self._backend.run_at(when, callback)
        self._task_descriptions[task_id] = {
            "tool": tool_name,
            "arguments": arguments,
            "runs_at": when.isoformat(),
            "recurring": False,
        }
        return {"success": True, "task_id": task_id, **self._task_descriptions[task_id]}

    def schedule_every(self, interval_seconds: float, tool_name: str, arguments: Dict = None) -> Dict:
        """Run a tool repeatedly, every interval_seconds (e.g. 'check email every 30 minutes')."""
        arguments = arguments or {}
        callback = self._make_callback(tool_name, arguments)
        task_id = self._backend.run_every(interval_seconds, callback)
        self._task_descriptions[task_id] = {
            "tool": tool_name,
            "arguments": arguments,
            "interval_seconds": interval_seconds,
            "recurring": True,
        }
        return {"success": True, "task_id": task_id, **self._task_descriptions[task_id]}

    def cancel(self, task_id: str) -> Dict:
        """Cancel a scheduled task."""
        ok = self._backend.cancel(task_id)
        if ok:
            self._task_descriptions.pop(task_id, None)
            return {"success": True, "cancelled": task_id}
        return {"error": f"No scheduled task with id '{task_id}'"}

    def list_scheduled(self) -> Dict:
        """List all currently scheduled tasks with their tool + timing info."""
        return {"count": len(self._task_descriptions), "tasks": self._task_descriptions}
