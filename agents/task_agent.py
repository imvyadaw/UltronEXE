"""
Task agent
==========
Two different notions of "task" live in Ultron and this agent fronts
both of them under one name:

- A persistent to-do list (SQLite) for things the *user* needs to do -
  "remind me to renew my passport".
- core/task_queue.py's background job runner, for things *Ultron* needs
  to run without blocking the voice/text loop - "check my inbox every
  10 minutes".
"""

import sqlite3
import time
import uuid
from pathlib import Path
from typing import Callable, Dict

from agents.base_agent import BaseAgent

DB_PATH = Path(__file__).resolve().parent.parent / "storage" / "sqlite" / "todos.db"


def _task_queue():
    from core.task_queue import get_task_queue

    return get_task_queue()


class TaskAgent(BaseAgent):
    """Persistent to-do list + background task submission."""

    capabilities = ["task", "todo", "reminders", "background jobs"]

    def __init__(self):
        super().__init__("task", "Persistent to-do list + background task submission")
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
        self._conn.execute("""CREATE TABLE IF NOT EXISTS todos (
                id TEXT PRIMARY KEY,
                text TEXT,
                priority TEXT,
                due TEXT,
                done INTEGER DEFAULT 0,
                created_at REAL
            )""")
        self._conn.commit()

    # --- Persistent to-do list -------------------------------------------

    def add_todo(self, text: str, priority: str = "normal", due: str = None) -> Dict:
        """Add a to-do item. `priority` is a free-text label (low/normal/high)."""
        try:
            todo_id = str(uuid.uuid4())[:8]
            self._conn.execute(
                "INSERT INTO todos (id, text, priority, due, done, created_at) VALUES (?, ?, ?, ?, 0, ?)",
                (todo_id, text, priority, due, time.time()),
            )
            self._conn.commit()
            return {"success": True, "id": todo_id, "text": text}
        except Exception as e:
            return {"error": str(e)}

    def list_todos(self, include_done: bool = False) -> Dict:
        """List to-do items, most recent first."""
        try:
            cur = self._conn.cursor()
            if include_done:
                cur.execute("SELECT id, text, priority, due, done FROM todos ORDER BY created_at DESC")
            else:
                cur.execute("SELECT id, text, priority, due, done FROM todos WHERE done = 0 ORDER BY created_at DESC")
            rows = cur.fetchall()
            todos = [{"id": r[0], "text": r[1], "priority": r[2], "due": r[3], "done": bool(r[4])} for r in rows]
            return {"count": len(todos), "todos": todos}
        except Exception as e:
            return {"error": str(e)}

    def complete_todo(self, todo_id: str) -> Dict:
        """Mark a to-do item as done."""
        try:
            cur = self._conn.cursor()
            cur.execute("UPDATE todos SET done = 1 WHERE id = ?", (todo_id,))
            self._conn.commit()
            if cur.rowcount == 0:
                return {"error": f"No to-do found with id {todo_id}"}
            return {"success": True, "id": todo_id}
        except Exception as e:
            return {"error": str(e)}

    def delete_todo(self, todo_id: str) -> Dict:
        """Delete a to-do item outright."""
        try:
            cur = self._conn.cursor()
            cur.execute("DELETE FROM todos WHERE id = ?", (todo_id,))
            self._conn.commit()
            if cur.rowcount == 0:
                return {"error": f"No to-do found with id {todo_id}"}
            return {"success": True, "deleted_id": todo_id}
        except Exception as e:
            return {"error": str(e)}

    # --- Background jobs (core/task_queue.py) -----------------------------

    def run_in_background(self, func: Callable, *args, label: str = "", **kwargs) -> Dict:
        """Submit a callable to run on a worker thread; returns immediately
        with a task_id to poll via task_status()."""
        task_id = _task_queue().submit(func, *args, label=label, **kwargs)
        return {"success": True, "task_id": task_id, "label": label}

    def task_status(self, task_id: str) -> Dict:
        return _task_queue().get_status(task_id)

    def list_background_tasks(self, status: str = None) -> Dict:
        return _task_queue().list_tasks(status)
