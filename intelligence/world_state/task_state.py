"""
Task State (Phase 19.1 - World State)
======================================
World-model view of "what tasks currently exist and what state are
they in" - pending / active / done / failed / cancelled - so
active_context.py can point at one by id and context_snapshot.py can
report "what's in flight right now". This is deliberately separate
from core/task_queue.py, which schedules and executes Ultron's own
internal tool-call queue: task_state here is a lighter-weight status
board that can represent *any* task worth tracking (a user's request,
a background job, a reminder someone else's code created), and
doesn't execute anything itself.
"""

import json
import sqlite3
import threading
import time
import uuid
from pathlib import Path
from typing import Dict, List, Optional

DB_PATH = Path(__file__).resolve().parent.parent.parent / "database" / "world_state.db"

VALID_STATUSES = ("pending", "active", "done", "failed", "cancelled")

_instance: Optional["TaskState"] = None
_instance_lock = threading.Lock()


class TaskState:
    """CRUD registry of tracked tasks and their status."""

    def __init__(self, db_path: Path = DB_PATH):
        self._db_path = db_path
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
        self._conn.execute("""CREATE TABLE IF NOT EXISTS tasks (
                id TEXT PRIMARY KEY,
                title TEXT,
                status TEXT,
                priority TEXT,
                source TEXT,
                metadata TEXT,
                created_at REAL,
                updated_at REAL,
                completed_at REAL
            )""")
        self._conn.commit()

    # -- writes -------------------------------------------------------------
    def create_task(
        self,
        title: str,
        priority: str = "normal",
        source: str = "user",
        metadata: Optional[Dict] = None,
    ) -> Dict:
        """Register a new tracked task in 'pending' status. Returns the
        created task record (with its generated id)."""
        if not title:
            return {"error": "title required"}
        task_id = uuid.uuid4().hex[:12]
        now = time.time()
        with self._lock:
            self._conn.execute(
                """INSERT INTO tasks (id, title, status, priority, source, metadata, created_at, updated_at, completed_at)
                   VALUES (?, ?, 'pending', ?, ?, ?, ?, ?, NULL)""",
                (task_id, title, priority, source, json.dumps(metadata or {}), now, now),
            )
            self._conn.commit()
        return self.get_task(task_id)

    def update_status(self, task_id: str, status: str) -> Dict:
        """Move a task to a new status. Setting 'done', 'failed', or
        'cancelled' stamps completed_at."""
        if status not in VALID_STATUSES:
            return {"error": f"status must be one of {VALID_STATUSES}"}
        existing = self.get_task(task_id)
        if "error" in existing:
            return existing
        now = time.time()
        completed_at = now if status in ("done", "failed", "cancelled") else None
        with self._lock:
            self._conn.execute(
                "UPDATE tasks SET status = ?, updated_at = ?, completed_at = ? WHERE id = ?",
                (status, now, completed_at, task_id),
            )
            self._conn.commit()
        return self.get_task(task_id)

    def complete_task(self, task_id: str) -> Dict:
        """Shorthand for update_status(task_id, 'done')."""
        return self.update_status(task_id, "done")

    def delete_task(self, task_id: str) -> Dict:
        with self._lock:
            self._conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
            self._conn.commit()
        return {"success": True, "id": task_id}

    # -- reads ----------------------------------------------------------------
    def get_task(self, task_id: str) -> Dict:
        with self._lock:
            cur = self._conn.execute(
                """SELECT id, title, status, priority, source, metadata, created_at, updated_at, completed_at
                   FROM tasks WHERE id = ?""",
                (task_id,),
            )
            row = cur.fetchone()
        if row is None:
            return {"error": f"no task with id {task_id}"}
        return self._row_to_dict(row)

    def list_tasks(self, status: Optional[str] = None, limit: int = 100) -> List[Dict]:
        """All tracked tasks, most recently updated first, optionally
        filtered to one status."""
        with self._lock:
            if status:
                cur = self._conn.execute(
                    """SELECT id, title, status, priority, source, metadata, created_at, updated_at, completed_at
                       FROM tasks WHERE status = ? ORDER BY updated_at DESC LIMIT ?""",
                    (status, limit),
                )
            else:
                cur = self._conn.execute(
                    """SELECT id, title, status, priority, source, metadata, created_at, updated_at, completed_at
                       FROM tasks ORDER BY updated_at DESC LIMIT ?""",
                    (limit,),
                )
            rows = cur.fetchall()
        return [self._row_to_dict(r) for r in rows]

    def active_tasks(self, limit: int = 100) -> List[Dict]:
        """Tasks currently 'pending' or 'active' - the ones still in flight."""
        with self._lock:
            cur = self._conn.execute(
                """SELECT id, title, status, priority, source, metadata, created_at, updated_at, completed_at
                   FROM tasks WHERE status IN ('pending', 'active') ORDER BY updated_at DESC LIMIT ?""",
                (limit,),
            )
            rows = cur.fetchall()
        return [self._row_to_dict(r) for r in rows]

    @staticmethod
    def _row_to_dict(row) -> Dict:
        try:
            metadata = json.loads(row[5]) if row[5] else {}
        except Exception:
            metadata = {}
        return {
            "id": row[0],
            "title": row[1],
            "status": row[2],
            "priority": row[3],
            "source": row[4],
            "metadata": metadata,
            "created_at": row[6],
            "updated_at": row[7],
            "completed_at": row[8],
        }


def get_task_state() -> TaskState:
    """Process-wide TaskState singleton."""
    global _instance
    if _instance is None:
        with _instance_lock:
            if _instance is None:
                _instance = TaskState()
    return _instance
