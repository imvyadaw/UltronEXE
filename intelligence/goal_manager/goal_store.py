"""
Goal Store (Phase 19.3 - Goal Manager)
=========================================
Lowest layer of the goal_manager/ package: plain sqlite CRUD for
goals, their ordered steps, and an append-only event log (created,
step_added, step_completed, paused, resumed, stalled_detected,
recovery_attempted, completed, abandoned, ...). Nothing here
decomposes, tracks progress, or decides anything - it only stores
and retrieves. goal_decomposer.py, progress_tracker.py,
pause_resume.py, and recovery_manager.py all sit on top of this and
are the modules that add behavior.

Storage: database/goals.db, tables goals / goal_steps / goal_events.
"""

import json
import sqlite3
import threading
import time
import uuid
from pathlib import Path
from typing import Dict, List, Optional

DB_PATH = Path(__file__).resolve().parent.parent.parent / "database" / "goals.db"

VALID_GOAL_STATUSES = ("active", "paused", "completed", "abandoned")
VALID_STEP_STATUSES = ("pending", "in_progress", "done", "skipped")

_instance: Optional["GoalStore"] = None
_instance_lock = threading.Lock()


class GoalStore:
    """Persistence for goals, their steps, and the event log. Every
    write also appends a row to goal_events so pause_resume.py and
    recovery_manager.py can reason about "when did anything last
    happen on this goal" without each keeping their own log."""

    def __init__(self, db_path: Path = DB_PATH):
        self._db_path = db_path
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
        self._conn.execute("""CREATE TABLE IF NOT EXISTS goals (
                id TEXT PRIMARY KEY,
                title TEXT,
                description TEXT,
                status TEXT,
                priority TEXT,
                deadline REAL,
                linked_intent_goal_id TEXT,
                created_at REAL,
                updated_at REAL,
                completed_at REAL
            )""")
        self._conn.execute("""CREATE TABLE IF NOT EXISTS goal_steps (
                id TEXT PRIMARY KEY,
                goal_id TEXT,
                description TEXT,
                order_index INTEGER,
                status TEXT,
                created_at REAL,
                completed_at REAL
            )""")
        self._conn.execute("""CREATE TABLE IF NOT EXISTS goal_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                goal_id TEXT,
                event_type TEXT,
                payload_json TEXT,
                timestamp REAL
            )""")
        self._conn.commit()

    # -- goals ----------------------------------------------------------------
    def create_goal(
        self,
        title: str,
        description: str = "",
        priority: str = "normal",
        deadline: Optional[float] = None,
        linked_intent_goal_id: Optional[str] = None,
    ) -> Dict:
        if not title:
            return {"error": "title required"}
        goal_id = uuid.uuid4().hex[:12]
        now = time.time()
        with self._lock:
            self._conn.execute(
                """INSERT INTO goals
                   (id, title, description, status, priority, deadline,
                    linked_intent_goal_id, created_at, updated_at, completed_at)
                   VALUES (?, ?, ?, 'active', ?, ?, ?, ?, ?, NULL)""",
                (goal_id, title, description, priority, deadline, linked_intent_goal_id, now, now),
            )
            self._conn.commit()
        self.log_event(goal_id, "created", {"title": title})
        return self.get_goal(goal_id)

    def get_goal(self, goal_id: str) -> Dict:
        with self._lock:
            cur = self._conn.execute(
                """SELECT id, title, description, status, priority, deadline,
                          linked_intent_goal_id, created_at, updated_at, completed_at
                   FROM goals WHERE id = ?""",
                (goal_id,),
            )
            row = cur.fetchone()
        if row is None:
            return {"error": f"no goal with id {goal_id}"}
        return self._goal_row_to_dict(row)

    def list_goals(self, status: Optional[str] = None) -> List[Dict]:
        with self._lock:
            if status:
                cur = self._conn.execute(
                    """SELECT id, title, description, status, priority, deadline,
                              linked_intent_goal_id, created_at, updated_at, completed_at
                       FROM goals WHERE status = ? ORDER BY created_at DESC""",
                    (status,),
                )
            else:
                cur = self._conn.execute("""SELECT id, title, description, status, priority, deadline,
                              linked_intent_goal_id, created_at, updated_at, completed_at
                       FROM goals ORDER BY created_at DESC""")
            rows = cur.fetchall()
        return [self._goal_row_to_dict(r) for r in rows]

    def update_goal(self, goal_id: str, **fields) -> Dict:
        """Patch arbitrary columns on a goal (status, priority, deadline,
        description, title). Always bumps updated_at; sets completed_at
        automatically when status is set to 'completed'."""
        if self.get_goal(goal_id).get("error"):
            return {"error": f"no goal with id {goal_id}"}
        allowed = {"title", "description", "status", "priority", "deadline", "linked_intent_goal_id"}
        sets, values = [], []
        for key, value in fields.items():
            if key not in allowed:
                continue
            if key == "status" and value not in VALID_GOAL_STATUSES:
                return {"error": f"invalid status {value}"}
            sets.append(f"{key} = ?")
            values.append(value)
        if not sets:
            return self.get_goal(goal_id)
        now = time.time()
        sets.append("updated_at = ?")
        values.append(now)
        if fields.get("status") == "completed":
            sets.append("completed_at = ?")
            values.append(now)
        values.append(goal_id)
        with self._lock:
            self._conn.execute(f"UPDATE goals SET {', '.join(sets)} WHERE id = ?", values)
            self._conn.commit()
        return self.get_goal(goal_id)

    def delete_goal(self, goal_id: str) -> Dict:
        with self._lock:
            self._conn.execute("DELETE FROM goals WHERE id = ?", (goal_id,))
            self._conn.execute("DELETE FROM goal_steps WHERE goal_id = ?", (goal_id,))
            self._conn.execute("DELETE FROM goal_events WHERE goal_id = ?", (goal_id,))
            self._conn.commit()
        return {"success": True, "id": goal_id}

    # -- steps ------------------------------------------------------------------
    def add_step(self, goal_id: str, description: str, order_index: Optional[int] = None) -> Dict:
        if self.get_goal(goal_id).get("error"):
            return {"error": f"no goal with id {goal_id}"}
        if order_index is None:
            order_index = len(self.list_steps(goal_id))
        step_id = uuid.uuid4().hex[:12]
        now = time.time()
        with self._lock:
            self._conn.execute(
                """INSERT INTO goal_steps
                   (id, goal_id, description, order_index, status, created_at, completed_at)
                   VALUES (?, ?, ?, ?, 'pending', ?, NULL)""",
                (step_id, goal_id, description, order_index, now),
            )
            self._conn.commit()
        self.log_event(goal_id, "step_added", {"step_id": step_id, "description": description})
        return self.get_step(step_id)

    def get_step(self, step_id: str) -> Dict:
        with self._lock:
            cur = self._conn.execute(
                """SELECT id, goal_id, description, order_index, status, created_at, completed_at
                   FROM goal_steps WHERE id = ?""",
                (step_id,),
            )
            row = cur.fetchone()
        if row is None:
            return {"error": f"no step with id {step_id}"}
        return self._step_row_to_dict(row)

    def list_steps(self, goal_id: str) -> List[Dict]:
        with self._lock:
            cur = self._conn.execute(
                """SELECT id, goal_id, description, order_index, status, created_at, completed_at
                   FROM goal_steps WHERE goal_id = ? ORDER BY order_index ASC""",
                (goal_id,),
            )
            rows = cur.fetchall()
        return [self._step_row_to_dict(r) for r in rows]

    def update_step(self, step_id: str, status: str) -> Dict:
        if status not in VALID_STEP_STATUSES:
            return {"error": f"invalid status {status}"}
        step = self.get_step(step_id)
        if step.get("error"):
            return step
        now = time.time()
        completed_at = now if status == "done" else None
        with self._lock:
            self._conn.execute(
                "UPDATE goal_steps SET status = ?, completed_at = ? WHERE id = ?",
                (status, completed_at, step_id),
            )
            self._conn.commit()
        event_type = "step_completed" if status == "done" else "step_updated"
        self.log_event(step["goal_id"], event_type, {"step_id": step_id, "status": status})
        return self.get_step(step_id)

    # -- events -------------------------------------------------------------------
    def log_event(self, goal_id: str, event_type: str, payload: Optional[Dict] = None) -> Dict:
        now = time.time()
        with self._lock:
            self._conn.execute(
                """INSERT INTO goal_events (goal_id, event_type, payload_json, timestamp)
                   VALUES (?, ?, ?, ?)""",
                (goal_id, event_type, json.dumps(payload or {}, default=str), now),
            )
            self._conn.commit()
        return {"success": True}

    def list_events(self, goal_id: str, limit: int = 50) -> List[Dict]:
        with self._lock:
            cur = self._conn.execute(
                """SELECT id, goal_id, event_type, payload_json, timestamp
                   FROM goal_events WHERE goal_id = ? ORDER BY id DESC LIMIT ?""",
                (goal_id, limit),
            )
            rows = cur.fetchall()
        return [self._event_row_to_dict(r) for r in reversed(rows)]

    def last_event_time(self, goal_id: str) -> Optional[float]:
        with self._lock:
            cur = self._conn.execute(
                "SELECT timestamp FROM goal_events WHERE goal_id = ? ORDER BY id DESC LIMIT 1",
                (goal_id,),
            )
            row = cur.fetchone()
        return row[0] if row else None

    # -- row helpers ----------------------------------------------------------------
    @staticmethod
    def _goal_row_to_dict(row) -> Dict:
        return {
            "id": row[0],
            "title": row[1],
            "description": row[2],
            "status": row[3],
            "priority": row[4],
            "deadline": row[5],
            "linked_intent_goal_id": row[6],
            "created_at": row[7],
            "updated_at": row[8],
            "completed_at": row[9],
        }

    @staticmethod
    def _step_row_to_dict(row) -> Dict:
        return {
            "id": row[0],
            "goal_id": row[1],
            "description": row[2],
            "order_index": row[3],
            "status": row[4],
            "created_at": row[5],
            "completed_at": row[6],
        }

    @staticmethod
    def _event_row_to_dict(row) -> Dict:
        try:
            payload = json.loads(row[3]) if row[3] else {}
        except Exception:
            payload = {}
        return {"id": row[0], "goal_id": row[1], "event_type": row[2], "payload": payload, "timestamp": row[4]}


def get_goal_store() -> GoalStore:
    """Process-wide GoalStore singleton."""
    global _instance
    if _instance is None:
        with _instance_lock:
            if _instance is None:
                _instance = GoalStore()
    return _instance
