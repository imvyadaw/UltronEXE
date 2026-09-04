"""
Mission Store (P1 - Mission Persistence Engine)
================================================
Lowest layer of the mission_engine/ package: plain sqlite CRUD for
missions, their checkpoints, and an append-only event log.

A "mission" is deliberately a level above intelligence.goal_manager's
Goal: a Goal is one actionable objective inside a single planning
session; a Mission is the thing that survives Ultron restarting -
"help me plan the Bangalore trip", "get the tax filing done this
week" - which may span many goals, many conversations, and many days.
mission_manager.py links missions to one or more goal_ids from
intelligence.goal_manager rather than duplicating step-tracking here.

Storage: database/missions.db, tables missions / mission_checkpoints /
mission_events. Same style as intelligence/goal_manager/goal_store.py
on purpose, so both packages read the same way.
"""

import json
import sqlite3
import threading
import time
import uuid
from pathlib import Path
from typing import Dict, List, Optional

DB_PATH = Path(__file__).resolve().parent.parent.parent / "database" / "missions.db"

VALID_MISSION_STATUSES = ("active", "paused", "completed", "abandoned")

_instance: Optional["MissionStore"] = None
_instance_lock = threading.Lock()


class MissionStore:
    """Persistence for missions, their checkpoints (point-in-time state
    snapshots so a mission can be resumed with full context after a
    restart), and the event log."""

    def __init__(self, db_path: Path = DB_PATH):
        self._db_path = db_path
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
        self._conn.execute("""CREATE TABLE IF NOT EXISTS missions (
                id TEXT PRIMARY KEY,
                title TEXT,
                description TEXT,
                status TEXT,
                goal_ids_json TEXT,
                context_json TEXT,
                created_at REAL,
                updated_at REAL,
                last_active_at REAL,
                completed_at REAL,
                resumed_count INTEGER DEFAULT 0
            )""")
        self._conn.execute("""CREATE TABLE IF NOT EXISTS mission_checkpoints (
                id TEXT PRIMARY KEY,
                mission_id TEXT,
                note TEXT,
                state_json TEXT,
                created_at REAL
            )""")
        self._conn.execute("""CREATE TABLE IF NOT EXISTS mission_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                mission_id TEXT,
                event_type TEXT,
                payload_json TEXT,
                timestamp REAL
            )""")
        self._conn.commit()

    # -- events ---------------------------------------------------------
    def _log_event(self, mission_id: str, event_type: str, payload: Optional[Dict] = None):
        self._conn.execute(
            "INSERT INTO mission_events (mission_id, event_type, payload_json, timestamp) VALUES (?, ?, ?, ?)",
            (mission_id, event_type, json.dumps(payload or {}), time.time()),
        )

    # -- missions ---------------------------------------------------------
    def create_mission(self, title: str, description: str = "", context: Optional[Dict] = None) -> Dict:
        mission_id = str(uuid.uuid4())
        now = time.time()
        with self._lock:
            self._conn.execute(
                """INSERT INTO missions
                   (id, title, description, status, goal_ids_json, context_json,
                    created_at, updated_at, last_active_at, completed_at, resumed_count)
                   VALUES (?, ?, ?, 'active', '[]', ?, ?, ?, ?, NULL, 0)""",
                (mission_id, title, description, json.dumps(context or {}), now, now, now),
            )
            self._log_event(mission_id, "created", {"title": title})
            self._conn.commit()
        return self.get_mission(mission_id)

    def get_mission(self, mission_id: str) -> Optional[Dict]:
        row = self._conn.execute("SELECT * FROM missions WHERE id = ?", (mission_id,)).fetchone()
        return self._row_to_dict(row) if row else None

    def list_missions(self, status: Optional[str] = None) -> List[Dict]:
        if status:
            rows = self._conn.execute(
                "SELECT * FROM missions WHERE status = ? ORDER BY last_active_at DESC", (status,)
            ).fetchall()
        else:
            rows = self._conn.execute("SELECT * FROM missions ORDER BY last_active_at DESC").fetchall()
        return [self._row_to_dict(r) for r in rows]

    def update_status(self, mission_id: str, status: str) -> bool:
        if status not in VALID_MISSION_STATUSES:
            return False
        now = time.time()
        completed_at = now if status == "completed" else None
        with self._lock:
            cur = self._conn.execute(
                "UPDATE missions SET status = ?, updated_at = ?, last_active_at = ?, "
                "completed_at = COALESCE(?, completed_at) WHERE id = ?",
                (status, now, now, completed_at, mission_id),
            )
            self._log_event(mission_id, f"status_{status}")
            self._conn.commit()
        return cur.rowcount > 0

    def touch(self, mission_id: str):
        """Bump last_active_at without changing status - called whenever a
        mission is worked on so the most-recently-active mission is always
        the one auto-resume offers first."""
        with self._lock:
            self._conn.execute("UPDATE missions SET last_active_at = ? WHERE id = ?", (time.time(), mission_id))
            self._conn.commit()

    def link_goal(self, mission_id: str, goal_id: str) -> bool:
        mission = self.get_mission(mission_id)
        if not mission:
            return False
        goal_ids = mission["goal_ids"]
        if goal_id not in goal_ids:
            goal_ids.append(goal_id)
        with self._lock:
            self._conn.execute(
                "UPDATE missions SET goal_ids_json = ?, updated_at = ? WHERE id = ?",
                (json.dumps(goal_ids), time.time(), mission_id),
            )
            self._log_event(mission_id, "goal_linked", {"goal_id": goal_id})
            self._conn.commit()
        return True

    def increment_resumed_count(self, mission_id: str):
        with self._lock:
            self._conn.execute(
                "UPDATE missions SET resumed_count = resumed_count + 1, last_active_at = ? WHERE id = ?",
                (time.time(), mission_id),
            )
            self._log_event(mission_id, "resumed")
            self._conn.commit()

    def update_context(self, mission_id: str, context: Dict):
        with self._lock:
            self._conn.execute(
                "UPDATE missions SET context_json = ?, updated_at = ? WHERE id = ?",
                (json.dumps(context), time.time(), mission_id),
            )
            self._conn.commit()

    # -- checkpoints ------------------------------------------------------
    def add_checkpoint(self, mission_id: str, note: str, state: Optional[Dict] = None) -> Dict:
        checkpoint_id = str(uuid.uuid4())
        now = time.time()
        with self._lock:
            self._conn.execute(
                "INSERT INTO mission_checkpoints (id, mission_id, note, state_json, created_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (checkpoint_id, mission_id, note, json.dumps(state or {}), now),
            )
            self._conn.execute(
                "UPDATE missions SET last_active_at = ?, updated_at = ? WHERE id = ?",
                (now, now, mission_id),
            )
            self._log_event(mission_id, "checkpoint", {"note": note})
            self._conn.commit()
        return {"id": checkpoint_id, "mission_id": mission_id, "note": note, "state": state or {}, "created_at": now}

    def get_checkpoints(self, mission_id: str, limit: int = 20) -> List[Dict]:
        rows = self._conn.execute(
            "SELECT * FROM mission_checkpoints WHERE mission_id = ? ORDER BY created_at DESC LIMIT ?",
            (mission_id, limit),
        ).fetchall()
        return [
            {
                "id": r[0],
                "mission_id": r[1],
                "note": r[2],
                "state": json.loads(r[3]) if r[3] else {},
                "created_at": r[4],
            }
            for r in rows
        ]

    def get_events(self, mission_id: str, limit: int = 50) -> List[Dict]:
        rows = self._conn.execute(
            "SELECT event_type, payload_json, timestamp FROM mission_events "
            "WHERE mission_id = ? ORDER BY timestamp DESC LIMIT ?",
            (mission_id, limit),
        ).fetchall()
        return [{"event_type": r[0], "payload": json.loads(r[1]) if r[1] else {}, "timestamp": r[2]} for r in rows]

    # -- helpers ------------------------------------------------------
    @staticmethod
    def _row_to_dict(row) -> Dict:
        return {
            "id": row[0],
            "title": row[1],
            "description": row[2],
            "status": row[3],
            "goal_ids": json.loads(row[4]) if row[4] else [],
            "context": json.loads(row[5]) if row[5] else {},
            "created_at": row[6],
            "updated_at": row[7],
            "last_active_at": row[8],
            "completed_at": row[9],
            "resumed_count": row[10],
        }


def get_mission_store() -> MissionStore:
    global _instance
    if _instance is None:
        with _instance_lock:
            if _instance is None:
                _instance = MissionStore()
    return _instance
