"""
Workflow Recorder (Phase 19.6 - Skill Builder)
==================================================
Captures the raw material everything else in this package works
from: every action ULTRON performs (name + params + outcome), tagged
with a timestamp and, when a session is active, a session_id. Two
uses of the same log:
  - explicit recordings: start_recording() -> record_step() (...) ->
    stop_recording() groups a deliberate walkthrough into one
    ordered list of steps, ready for workflow_analyzer.py.
  - implicit history: workflow_detector.py mines the *untagged*
    stream (every action, session or not) for sequences that keep
    repeating on their own, without anyone explicitly recording them.

This module only records - it never analyzes, generalizes, or
decides what's worth turning into a skill.

Storage: database/learned_skills.db, tables action_log and
recording_sessions.
"""

import json
import sqlite3
import threading
import time
import uuid
from pathlib import Path
from typing import Dict, List, Optional

DB_PATH = Path(__file__).resolve().parent.parent.parent / "database" / "learned_skills.db"

_instance: Optional["WorkflowRecorder"] = None
_instance_lock = threading.Lock()


class WorkflowRecorder:
    """Logs every observed action, and groups them into named
    recording sessions on request."""

    def __init__(self, db_path: Path = DB_PATH):
        self._db_path = db_path
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
        self._conn.execute("""CREATE TABLE IF NOT EXISTS action_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT,
                action_name TEXT,
                params_json TEXT,
                success INTEGER,
                timestamp REAL
            )""")
        self._conn.execute("""CREATE TABLE IF NOT EXISTS recording_sessions (
                session_id TEXT PRIMARY KEY,
                name TEXT,
                status TEXT,
                started_at REAL,
                stopped_at REAL
            )""")
        self._conn.commit()

    def start_recording(self, name: Optional[str] = None) -> str:
        """Begin a new named session. Returns its session_id - pass
        that to record_step()/stop_recording() to make steps part of
        this walkthrough."""
        session_id = uuid.uuid4().hex[:12]
        now = time.time()
        with self._lock:
            self._conn.execute(
                """INSERT INTO recording_sessions (session_id, name, status, started_at, stopped_at)
                   VALUES (?, ?, 'recording', ?, NULL)""",
                (session_id, name or f"session_{session_id}", now),
            )
            self._conn.commit()
        return session_id

    def record_step(
        self, action_name: str, params: Optional[Dict] = None, success: bool = True, session_id: Optional[str] = None
    ) -> Dict:
        """Log one observed action. session_id is optional - omit it
        to just add to the general history for workflow_detector.py;
        pass an active session's id to also make it part of that
        recording."""
        now = time.time()
        with self._lock:
            self._conn.execute(
                """INSERT INTO action_log (session_id, action_name, params_json, success, timestamp)
                   VALUES (?, ?, ?, ?, ?)""",
                (session_id, action_name, json.dumps(params or {}), 1 if success else 0, now),
            )
            self._conn.commit()
        return {"success": True, "action_name": action_name, "session_id": session_id, "timestamp": now}

    def stop_recording(self, session_id: str) -> Dict:
        """Close the session and return its ordered steps, ready for
        workflow_analyzer.py. Safe to call on an already-stopped
        session (just returns its steps again)."""
        now = time.time()
        with self._lock:
            self._conn.execute(
                """UPDATE recording_sessions SET status = 'stopped', stopped_at = ?
                   WHERE session_id = ? AND status = 'recording'""",
                (now, session_id),
            )
            self._conn.commit()
        return {"session_id": session_id, "steps": self.get_session_steps(session_id)}

    def get_session_steps(self, session_id: str) -> List[Dict]:
        with self._lock:
            cur = self._conn.execute(
                """SELECT action_name, params_json, success, timestamp FROM action_log
                   WHERE session_id = ? ORDER BY id ASC""",
                (session_id,),
            )
            rows = cur.fetchall()
        return [self._row_to_step(r) for r in rows]

    def get_recent_actions(self, limit: int = 200) -> List[Dict]:
        """Most recent entries in the general action history,
        oldest-first, regardless of session - the raw material
        workflow_detector.py mines for repeating sequences."""
        with self._lock:
            cur = self._conn.execute(
                """SELECT action_name, params_json, success, timestamp FROM action_log
                   ORDER BY id DESC LIMIT ?""",
                (limit,),
            )
            rows = cur.fetchall()
        return [self._row_to_step(r) for r in reversed(rows)]

    def list_sessions(self, status: Optional[str] = None, limit: int = 50) -> List[Dict]:
        with self._lock:
            if status:
                cur = self._conn.execute(
                    """SELECT session_id, name, status, started_at, stopped_at FROM recording_sessions
                       WHERE status = ? ORDER BY started_at DESC LIMIT ?""",
                    (status, limit),
                )
            else:
                cur = self._conn.execute(
                    """SELECT session_id, name, status, started_at, stopped_at FROM recording_sessions
                       ORDER BY started_at DESC LIMIT ?""",
                    (limit,),
                )
            rows = cur.fetchall()
        return [
            {"session_id": r[0], "name": r[1], "status": r[2], "started_at": r[3], "stopped_at": r[4]} for r in rows
        ]

    @staticmethod
    def _row_to_step(row) -> Dict:
        action_name, params_json, success, timestamp = row
        try:
            params = json.loads(params_json) if params_json else {}
        except Exception:
            params = {}
        return {"action_name": action_name, "params": params, "success": bool(success), "timestamp": timestamp}


def get_workflow_recorder() -> WorkflowRecorder:
    """Process-wide WorkflowRecorder singleton."""
    global _instance
    if _instance is None:
        with _instance_lock:
            if _instance is None:
                _instance = WorkflowRecorder()
    return _instance
