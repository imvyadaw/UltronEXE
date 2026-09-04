"""
Task Queue
==========
Lightweight async task manager so a long tool call (or a whole workflow)
can run in the background instead of blocking the voice/text loop in
main.py. Backed by a small pool of daemon worker threads pulling from a
queue.Queue - no external dependencies, matches the rest of Ultron's
"stdlib + graceful degradation" style.

Usage:
    from core.task_queue import get_task_queue
    tq = get_task_queue()
    task_id = tq.submit(some_callable, "arg1", label="check inbox")
    tq.get_status(task_id)      # {"status": "running", ...}
    tq.list_tasks()
    tq.cancel(task_id)          # best-effort: only stops it if not yet started
"""

import queue
import threading
import time
import uuid
from typing import Any, Callable, Dict, List, Optional

from core.events import get_event_bus
from core.error_handler import get_error_handler
from core.logger import get_logger

logger = get_logger("ultron.task_queue")

_task_queue: Optional["TaskQueue"] = None
_lock = threading.Lock()

STATUS_PENDING = "pending"
STATUS_RUNNING = "running"
STATUS_DONE = "done"
STATUS_FAILED = "failed"
STATUS_CANCELLED = "cancelled"


class Task:
    def __init__(self, task_id: str, func: Callable, args: tuple, kwargs: dict, label: str):
        self.id = task_id
        self.func = func
        self.args = args
        self.kwargs = kwargs
        self.label = label or getattr(func, "__name__", "task")
        self.status = STATUS_PENDING
        self.result: Any = None
        self.error: Optional[str] = None
        self.created_at = time.time()
        self.started_at: Optional[float] = None
        self.finished_at: Optional[float] = None

    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "label": self.label,
            "status": self.status,
            "result": self.result,
            "error": self.error,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
        }


class TaskQueue:
    """Background task runner with a small fixed pool of worker threads."""

    def __init__(self, num_workers: int = 3, max_history: int = 200):
        self._q: "queue.Queue[str]" = queue.Queue()
        self._tasks: Dict[str, Task] = {}
        self._tasks_lock = threading.Lock()
        self._max_history = max_history
        self._workers: List[threading.Thread] = []
        for i in range(num_workers):
            t = threading.Thread(target=self._worker_loop, name=f"ultron-task-worker-{i}", daemon=True)
            t.start()
            self._workers.append(t)

    def submit(self, func: Callable, *args, label: str = "", max_retries: int = 0, **kwargs) -> str:
        """Queue `func(*args, **kwargs)` to run in the background. Returns a task_id."""
        task_id = uuid.uuid4().hex[:12]
        task = Task(task_id, func, args, kwargs, label)
        with self._tasks_lock:
            self._tasks[task_id] = task
            self._trim_history()
        self._q.put(task_id)
        logger.info(f"Task queued: {task_id} ({task.label})")
        return task_id

    def _trim_history(self) -> None:
        if len(self._tasks) <= self._max_history:
            return
        finished = sorted(
            (t for t in self._tasks.values() if t.status in (STATUS_DONE, STATUS_FAILED, STATUS_CANCELLED)),
            key=lambda t: t.finished_at or 0,
        )
        overflow = len(self._tasks) - self._max_history
        for t in finished[:overflow]:
            self._tasks.pop(t.id, None)

    def _worker_loop(self) -> None:
        eh = get_error_handler()
        bus = get_event_bus()
        while True:
            task_id = self._q.get()
            with self._tasks_lock:
                task = self._tasks.get(task_id)
            if task is None or task.status == STATUS_CANCELLED:
                self._q.task_done()
                continue

            task.status = STATUS_RUNNING
            task.started_at = time.time()
            bus.emit("task_started", task_id=task.id, label=task.label)

            outcome = eh.run_safely(task.func, *task.args, max_retries=0, context=task.label, **task.kwargs)
            task.finished_at = time.time()
            if outcome.get("success"):
                task.status = STATUS_DONE
                task.result = outcome.get("result")
                bus.emit("task_completed", task_id=task.id, label=task.label, result=task.result)
            else:
                task.status = STATUS_FAILED
                task.error = outcome.get("error")
                bus.emit("task_failed", task_id=task.id, label=task.label, error=task.error)

            self._q.task_done()

    def get_status(self, task_id: str) -> Dict:
        with self._tasks_lock:
            task = self._tasks.get(task_id)
        if not task:
            return {"error": f"No task with id '{task_id}'"}
        return task.to_dict()

    def list_tasks(self, status: Optional[str] = None, limit: int = 20) -> Dict:
        with self._tasks_lock:
            tasks = sorted(self._tasks.values(), key=lambda t: t.created_at, reverse=True)
        if status:
            tasks = [t for t in tasks if t.status == status]
        tasks = tasks[:limit]
        return {"count": len(tasks), "tasks": [t.to_dict() for t in tasks]}

    def cancel(self, task_id: str) -> Dict:
        """Best-effort cancel: only prevents a still-pending task from
        starting. A task already running to completion (Ultron has no
        preemption mechanism for arbitrary Python callables)."""
        with self._tasks_lock:
            task = self._tasks.get(task_id)
            if not task:
                return {"error": f"No task with id '{task_id}'"}
            if task.status != STATUS_PENDING:
                return {"success": False, "error": f"Task is already '{task.status}', cannot cancel"}
            task.status = STATUS_CANCELLED
            task.finished_at = time.time()
        return {"success": True, "cancelled": task_id}


def get_task_queue() -> TaskQueue:
    global _task_queue
    with _lock:
        if _task_queue is None:
            _task_queue = TaskQueue()
        return _task_queue
