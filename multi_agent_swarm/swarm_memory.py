"""
Swarm memory
============
The swarm's shared "blackboard" - separate from memory/ and
PHASE_17_3_MEMORY_SYSTEM/, which are about what Ultron remembers about
the *user*. This is about what the swarm remembers about *itself*:
every task it was given and how it was resolved, a key/value scratch
space agents can read/write to coordinate without going through
agent_communication.py for every little thing, and a log of the
messages that did cross the bus (agent_communication.py calls
log_message() rather than persisting messages itself, same
separation-of-concerns as episodic_memory.py owning storage while
PHASE_17_3's wrapper owns interpretation).

Three SQLite tables, same sqlite3-and-a-Dict-per-method shape as
memory/episodic_memory.py and PHASE_17_3_MEMORY_SYSTEM's modules:

    tasks       - one row per subtask dispatched to a specialist:
                  status, assigned agent, result, timestamps
    blackboard  - free-form key/value scratch space, last-writer-wins,
                  tagged with which agent wrote it
    messages    - append-only log of everything sent over
                  agent_communication.py's bus
"""

import json
import sqlite3
import time
from pathlib import Path
from typing import Any, Dict, Optional

DB_PATH = Path(__file__).resolve().parents[1] / "storage" / "sqlite" / "swarm_memory.db"


class SwarmMemory:
    """Shared blackboard + task/message log for the agent swarm."""

    def __init__(self):
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        # check_same_thread=False: agent_orchestrator.py may dispatch
        # specialists across a thread pool for parallel execution, and
        # they can all end up recording to the same SwarmMemory instance.
        self._conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
        self._conn.execute("""CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_type TEXT,
                description TEXT,
                assigned_agent TEXT,
                status TEXT,
                result TEXT,
                created_at REAL,
                completed_at REAL
            )""")
        self._conn.execute("""CREATE TABLE IF NOT EXISTS blackboard (
                key TEXT PRIMARY KEY,
                value TEXT,
                updated_by TEXT,
                updated_at REAL
            )""")
        self._conn.execute("""CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                from_agent TEXT,
                to_agent TEXT,
                content TEXT,
                sent_at REAL
            )""")
        self._conn.commit()

    # -- tasks ------------------------------------------------------------
    def record_task(self, task_type: str, description: str, assigned_agent: str) -> Dict:
        """Log a subtask as it's dispatched. Returns the new task's id -
        pass it to update_task_status() once the specialist finishes."""
        try:
            cur = self._conn.execute(
                "INSERT INTO tasks (task_type, description, assigned_agent, status, result, created_at) "
                "VALUES (?, ?, ?, 'pending', NULL, ?)",
                (task_type, description, assigned_agent, time.time()),
            )
            self._conn.commit()
            return {"task_id": cur.lastrowid}
        except Exception as e:
            return {"error": str(e)}

    def update_task_status(self, task_id: int, status: str, result: Optional[Dict] = None) -> Dict:
        """Mark a task done/failed and store its result. `status` is
        typically 'completed' or 'failed'."""
        try:
            self._conn.execute(
                "UPDATE tasks SET status = ?, result = ?, completed_at = ? WHERE id = ?",
                (status, json.dumps(result) if result is not None else None, time.time(), task_id),
            )
            self._conn.commit()
            return {"task_id": task_id, "status": status}
        except Exception as e:
            return {"error": str(e)}

    def get_task(self, task_id: int) -> Dict:
        try:
            cur = self._conn.execute(
                "SELECT id, task_type, description, assigned_agent, status, result, created_at, completed_at "
                "FROM tasks WHERE id = ?",
                (task_id,),
            )
            row = cur.fetchone()
            if row is None:
                return {"error": f"No task with id {task_id}"}
            return _row_to_task(row)
        except Exception as e:
            return {"error": str(e)}

    def recent_tasks(self, limit: int = 20) -> Dict:
        try:
            cur = self._conn.execute(
                "SELECT id, task_type, description, assigned_agent, status, result, created_at, completed_at "
                "FROM tasks ORDER BY created_at DESC LIMIT ?",
                (limit,),
            )
            tasks = [_row_to_task(r) for r in cur.fetchall()]
            return {"count": len(tasks), "tasks": tasks}
        except Exception as e:
            return {"error": str(e)}

    # -- blackboard ---------------------------------------------------------
    def set_blackboard(self, key: str, value: Any, agent: str = "") -> Dict:
        """Write (or overwrite) a shared scratch value - last writer wins,
        same as PHASE_17_1_FOUNDATION's config_migrator layering, just
        for swarm-internal coordination state rather than settings."""
        try:
            self._conn.execute(
                "INSERT INTO blackboard (key, value, updated_by, updated_at) VALUES (?, ?, ?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_by = excluded.updated_by, "
                "updated_at = excluded.updated_at",
                (key, json.dumps(value), agent, time.time()),
            )
            self._conn.commit()
            return {"key": key, "updated_by": agent}
        except Exception as e:
            return {"error": str(e)}

    def get_blackboard(self, key: str) -> Dict:
        try:
            cur = self._conn.execute("SELECT value, updated_by, updated_at FROM blackboard WHERE key = ?", (key,))
            row = cur.fetchone()
            if row is None:
                return {"error": f"No blackboard entry for key '{key}'"}
            return {"key": key, "value": json.loads(row[0]), "updated_by": row[1], "updated_at": row[2]}
        except Exception as e:
            return {"error": str(e)}

    # -- messages -------------------------------------------------------
    def log_message(self, from_agent: str, to_agent: str, content: Dict) -> Dict:
        """Called by agent_communication.py's AgentBus after every send -
        this file owns persistence, the bus owns delivery."""
        try:
            self._conn.execute(
                "INSERT INTO messages (from_agent, to_agent, content, sent_at) VALUES (?, ?, ?, ?)",
                (from_agent, to_agent, json.dumps(content), time.time()),
            )
            self._conn.commit()
            return {"logged": True}
        except Exception as e:
            return {"error": str(e)}

    def recent_messages(self, limit: int = 50) -> Dict:
        try:
            cur = self._conn.execute(
                "SELECT from_agent, to_agent, content, sent_at FROM messages ORDER BY sent_at DESC LIMIT ?",
                (limit,),
            )
            messages = [
                {"from": r[0], "to": r[1], "content": json.loads(r[2]), "sent_at": r[3]} for r in cur.fetchall()
            ]
            return {"count": len(messages), "messages": messages}
        except Exception as e:
            return {"error": str(e)}


def _row_to_task(row) -> Dict:
    return {
        "id": row[0],
        "task_type": row[1],
        "description": row[2],
        "assigned_agent": row[3],
        "status": row[4],
        "result": json.loads(row[5]) if row[5] else None,
        "created_at": row[6],
        "completed_at": row[7],
    }


_swarm_memory: Optional[SwarmMemory] = None


def get_swarm_memory() -> SwarmMemory:
    """Process-wide singleton, same pattern as memory/*.py's get_*()."""
    global _swarm_memory
    if _swarm_memory is None:
        _swarm_memory = SwarmMemory()
    return _swarm_memory
