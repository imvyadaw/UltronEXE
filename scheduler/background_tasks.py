"""
Background Tasks (Phase 30 - Scheduler)
==========================================
core/task_queue.py runs a callable now, in the background.
core/scheduler.py runs a *tool* later (in/at/every). Neither knows
about the other, and a caller wanting "run this in the background,
whether that means immediately or on a schedule" (e.g.
autonomy/task_loop.py handing off a low-priority goal step so the
main loop isn't blocked) has to pick the right one itself and learn
two different status/cancel APIs.

BackgroundTasks is that single submit-and-track surface: submit_now()
delegates straight to task_queue, submit_later()/submit_recurring()
delegate straight to scheduler, and status()/cancel() work against
either kind of task_id without the caller needing to remember which
backend it came from.
"""

from typing import Any, Callable, Dict, Optional

from core.logger import get_logger
from core.task_queue import get_task_queue
from core.scheduler import Scheduler

logger = get_logger("ultron.scheduler.background_tasks")


class BackgroundTasks:
    def __init__(self):
        self._queue = get_task_queue()
        self._scheduler = Scheduler()
        # Track which backend owns which task_id so status()/cancel()
        # can route without the caller needing to know.
        self._owner: Dict[str, str] = {}

    def submit_now(self, fn: Callable, *args, label: str = "", **kwargs) -> str:
        task_id = self._queue.submit(fn, *args, label=label, **kwargs)
        self._owner[task_id] = "queue"
        return task_id

    def submit_later(self, seconds: float, tool_name: str, arguments: Optional[Dict[str, Any]] = None) -> Dict:
        result = self._scheduler.schedule_in(seconds, tool_name, arguments or {})
        task_id = result.get("task_id")
        if task_id:
            self._owner[task_id] = "scheduler"
        return result

    def submit_at(self, when_iso: str, tool_name: str, arguments: Optional[Dict[str, Any]] = None) -> Dict:
        result = self._scheduler.schedule_at(when_iso, tool_name, arguments or {})
        task_id = result.get("task_id")
        if task_id:
            self._owner[task_id] = "scheduler"
        return result

    def submit_recurring(
        self, interval_seconds: float, tool_name: str, arguments: Optional[Dict[str, Any]] = None
    ) -> Dict:
        result = self._scheduler.schedule_every(interval_seconds, tool_name, arguments or {})
        task_id = result.get("task_id")
        if task_id:
            self._owner[task_id] = "scheduler"
        return result

    def status(self, task_id: str) -> Dict:
        owner = self._owner.get(task_id)
        if owner == "queue":
            return self._queue.get_status(task_id)
        if owner == "scheduler":
            # Bug found while wiring this into ai/scheduler_tools.py:
            # Scheduler.list_scheduled() returns {"count": N, "tasks": {task_id: {...}}}
            # (a dict keyed by task_id) - this used to look for a "scheduled"
            # key holding a list of {"task_id": ...} dicts, which never
            # existed, so every lookup silently fell through to "not_found"
            # even for a task that was genuinely still scheduled (verified:
            # cancel() on the same task_id succeeded right after this
            # returned not_found). Fixed to read the real shape.
            task = self._scheduler.list_scheduled().get("tasks", {}).get(task_id)
            if task is not None:
                return {"status": "scheduled", "task_id": task_id, **task}
            return {"status": "not_found"}
        return {"status": "unknown_task_id"}

    def cancel(self, task_id: str) -> Dict:
        owner = self._owner.get(task_id)
        if owner == "queue":
            return self._queue.cancel(task_id)
        if owner == "scheduler":
            return self._scheduler.cancel(task_id)
        return {"success": False, "error": "unknown task_id"}


_instance: Optional[BackgroundTasks] = None


def get_background_tasks() -> BackgroundTasks:
    global _instance
    if _instance is None:
        _instance = BackgroundTasks()
    return _instance
