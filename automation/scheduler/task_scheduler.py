"""Low-level task scheduler
=========================
Runs Python callables at a specific time, after a delay, or repeatedly
on an interval, using a single background thread (no extra
dependencies - just `threading` + `time`). This is the low-level timer;
core/scheduler.py builds the Ultron-level "what task fires" logic on
top of it.
"""

import threading
import time
import uuid
from datetime import datetime
from typing import Callable, Dict, Optional


class TaskScheduler:
    """Background-thread task scheduler: run-once, delayed, or recurring."""

    def __init__(self):
        self._tasks: Dict[str, Dict] = {}
        self._lock = threading.Lock()
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def _loop(self):
        while self._running:
            now = time.time()
            with self._lock:
                due_ids = [tid for tid, t in self._tasks.items() if t["next_run"] <= now]
            for tid in due_ids:
                with self._lock:
                    task = self._tasks.get(tid)
                    if not task:
                        continue
                try:
                    task["callback"]()
                except Exception as e:
                    print(f"[TaskScheduler] Task '{tid}' raised: {e}")
                with self._lock:
                    if tid in self._tasks:
                        if task["interval_seconds"]:
                            self._tasks[tid]["next_run"] = now + task["interval_seconds"]
                        else:
                            del self._tasks[tid]
            time.sleep(1)

    def run_after(self, delay_seconds: float, callback: Callable, task_id: str = None) -> str:
        """Run `callback` once, after delay_seconds."""
        task_id = task_id or str(uuid.uuid4())[:8]
        with self._lock:
            self._tasks[task_id] = {
                "callback": callback,
                "next_run": time.time() + delay_seconds,
                "interval_seconds": None,
                "created": datetime.now().isoformat(),
            }
        return task_id

    def run_at(self, when: datetime, callback: Callable, task_id: str = None) -> str:
        """Run `callback` once, at a specific datetime."""
        delay = max(0, (when - datetime.now()).total_seconds())
        return self.run_after(delay, callback, task_id)

    def run_every(self, interval_seconds: float, callback: Callable, task_id: str = None) -> str:
        """Run `callback` repeatedly, every interval_seconds, starting after the first interval."""
        task_id = task_id or str(uuid.uuid4())[:8]
        with self._lock:
            self._tasks[task_id] = {
                "callback": callback,
                "next_run": time.time() + interval_seconds,
                "interval_seconds": interval_seconds,
                "created": datetime.now().isoformat(),
            }
        return task_id

    def cancel(self, task_id: str) -> bool:
        """Cancel a scheduled task by id."""
        with self._lock:
            if task_id in self._tasks:
                del self._tasks[task_id]
                return True
        return False

    def list_tasks(self) -> Dict:
        """List all currently scheduled tasks."""
        with self._lock:
            return {
                tid: {
                    "next_run": datetime.fromtimestamp(t["next_run"]).isoformat(),
                    "recurring": t["interval_seconds"] is not None,
                    "interval_seconds": t["interval_seconds"],
                    "created": t["created"],
                }
                for tid, t in self._tasks.items()
            }

    def shutdown(self):
        """Stop the background thread (tasks stop firing)."""
        self._running = False


# Module-level singleton so the whole app shares one background thread.
_scheduler_instance: Optional[TaskScheduler] = None


def get_scheduler() -> TaskScheduler:
    global _scheduler_instance
    if _scheduler_instance is None:
        _scheduler_instance = TaskScheduler()
    return _scheduler_instance
