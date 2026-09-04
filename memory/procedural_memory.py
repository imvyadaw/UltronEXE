"""Procedural memory
==================
Stores named, ordered step-sequences Ultron has learned to perform -
the "how to do X" layer, distinct from semantic memory's facts and
episodic memory's event log. A saved procedure is a list of
{"tool": ..., "arguments": {...}} steps, the exact shape
core/executor.py and core/workflow_engine.py already consume, so a
learned procedure can be handed straight to the workflow engine to
replay - this module is just the durable store + usage-tracking layer
core/workflow_engine.py doesn't have on its own.
"""

import json
import sqlite3
import time
from pathlib import Path
from typing import Dict, List

DB_PATH = Path(__file__).resolve().parent.parent / "storage" / "sqlite" / "procedural_memory.db"


class ProceduralMemory:
    """Named, ordered step-sequences ("how to do X"), with usage stats."""

    def __init__(self):
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
        self._conn.execute("""CREATE TABLE IF NOT EXISTS procedures (
                name TEXT PRIMARY KEY,
                description TEXT,
                steps TEXT,
                times_used INTEGER DEFAULT 0,
                created_at REAL,
                last_used_at REAL
            )""")
        self._conn.commit()

    def save_procedure(self, name: str, steps: List[Dict], description: str = "") -> Dict:
        """Save (or overwrite) a named procedure. Each step should be
        {"tool": "tool_name", "arguments": {...}} to match
        core/executor.execute_tool's signature."""
        try:
            self._conn.execute(
                "INSERT INTO procedures (name, description, steps, times_used, created_at, last_used_at) "
                "VALUES (?, ?, ?, 0, ?, NULL) "
                "ON CONFLICT(name) DO UPDATE SET description = excluded.description, steps = excluded.steps",
                (name, description, json.dumps(steps), time.time()),
            )
            self._conn.commit()
            return {"success": True, "name": name, "step_count": len(steps)}
        except Exception as e:
            return {"error": str(e)}

    def get_procedure(self, name: str) -> Dict:
        """Fetch a saved procedure's steps."""
        try:
            cur = self._conn.cursor()
            cur.execute("SELECT description, steps, times_used FROM procedures WHERE name = ?", (name,))
            row = cur.fetchone()
            if not row:
                return {"error": f"No procedure named '{name}'"}
            return {"name": name, "description": row[0], "steps": json.loads(row[1]), "times_used": row[2]}
        except Exception as e:
            return {"error": str(e)}

    def list_procedures(self) -> Dict:
        """List all saved procedures with their step counts."""
        try:
            cur = self._conn.cursor()
            cur.execute("SELECT name, description, steps, times_used FROM procedures ORDER BY times_used DESC")
            rows = cur.fetchall()
            procedures = [
                {"name": r[0], "description": r[1], "step_count": len(json.loads(r[2])), "times_used": r[3]}
                for r in rows
            ]
            return {"count": len(procedures), "procedures": procedures}
        except Exception as e:
            return {"error": str(e)}

    def mark_used(self, name: str) -> Dict:
        """Bump usage stats - call this each time a procedure is replayed,
        so list_procedures() can surface the most relied-upon ones first."""
        try:
            cur = self._conn.cursor()
            cur.execute(
                "UPDATE procedures SET times_used = times_used + 1, last_used_at = ? WHERE name = ?",
                (time.time(), name),
            )
            self._conn.commit()
            if cur.rowcount == 0:
                return {"error": f"No procedure named '{name}'"}
            return {"success": True, "name": name}
        except Exception as e:
            return {"error": str(e)}

    def delete_procedure(self, name: str) -> Dict:
        try:
            cur = self._conn.cursor()
            cur.execute("DELETE FROM procedures WHERE name = ?", (name,))
            self._conn.commit()
            if cur.rowcount == 0:
                return {"error": f"No procedure named '{name}'"}
            return {"success": True, "deleted": name}
        except Exception as e:
            return {"error": str(e)}
