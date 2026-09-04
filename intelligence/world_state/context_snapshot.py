"""
Context Snapshot (Phase 19.1 - World State)
==============================================
Pulls pc_state.py, active_context.py, task_state.py, device_state.py,
and environment_state.py together into one consolidated dict - "the
whole world model, right now" - and persists snapshots to
database/world_state.db so "what did the world look like at time T"
and before/after diffs are answerable later. world_state_manager.py
is the intended caller for build()/save(); this module imports its
sibling singletons lazily (inside the methods, not at module load
time) so it has no hard import-order dependency on world_state_manager.py
and can be exercised standalone.
"""

import json
import sqlite3
import threading
import time
from pathlib import Path
from typing import Dict, List, Optional

DB_PATH = Path(__file__).resolve().parent.parent.parent / "database" / "world_state.db"

_instance: Optional["ContextSnapshot"] = None
_instance_lock = threading.Lock()


class ContextSnapshot:
    """Builds, persists, and diffs consolidated world-state snapshots."""

    def __init__(self, db_path: Path = DB_PATH):
        self._db_path = db_path
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
        self._conn.execute("""CREATE TABLE IF NOT EXISTS snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                snapshot_json TEXT,
                created_at REAL
            )""")
        self._conn.commit()

    # -- build --------------------------------------------------------------
    def build(self) -> Dict:
        """Collect current() readings from every world-state sub-module into
        one dict. Individual sub-modules that fail to import/read don't
        block the rest - their section is set to {"error": ...} instead."""
        snapshot = {"timestamp": time.time()}

        try:
            from intelligence.world_state.pc_state import get_pc_state

            snapshot["pc"] = get_pc_state().current()
        except Exception as e:
            snapshot["pc"] = {"error": str(e)}

        try:
            from intelligence.world_state.active_context import get_active_context

            snapshot["active_context"] = get_active_context().current()
        except Exception as e:
            snapshot["active_context"] = {"error": str(e)}

        try:
            from intelligence.world_state.task_state import get_task_state

            snapshot["active_tasks"] = get_task_state().active_tasks()
        except Exception as e:
            snapshot["active_tasks"] = {"error": str(e)}

        try:
            from intelligence.world_state.device_state import get_device_state

            snapshot["connected_devices"] = get_device_state().connected_devices()
        except Exception as e:
            snapshot["connected_devices"] = {"error": str(e)}

        try:
            from intelligence.world_state.environment_state import get_environment_state

            snapshot["environment"] = get_environment_state().snapshot()
        except Exception as e:
            snapshot["environment"] = {"error": str(e)}

        return snapshot

    # -- persistence ------------------------------------------------------
    def save(self, snapshot: Optional[Dict] = None) -> Dict:
        """Persist a snapshot (builds a fresh one via build() if none is
        given). Returns {"success": True, "id": ...}."""
        snapshot = snapshot if snapshot is not None else self.build()
        with self._lock:
            cur = self._conn.execute(
                "INSERT INTO snapshots (snapshot_json, created_at) VALUES (?, ?)",
                (json.dumps(snapshot, default=str), snapshot.get("timestamp", time.time())),
            )
            self._conn.commit()
            snapshot_id = cur.lastrowid
        return {"success": True, "id": snapshot_id, "snapshot": snapshot}

    def latest(self) -> Optional[Dict]:
        """Most recently saved snapshot, or None if none have been saved yet."""
        with self._lock:
            cur = self._conn.execute(
                "SELECT id, snapshot_json, created_at FROM snapshots ORDER BY created_at DESC LIMIT 1"
            )
            row = cur.fetchone()
        if row is None:
            return None
        return self._row_to_dict(row)

    def history(self, limit: int = 20) -> List[Dict]:
        """Most recently saved snapshots, newest first."""
        with self._lock:
            cur = self._conn.execute(
                "SELECT id, snapshot_json, created_at FROM snapshots ORDER BY created_at DESC LIMIT ?",
                (limit,),
            )
            rows = cur.fetchall()
        return [self._row_to_dict(r) for r in rows]

    def get(self, snapshot_id: int) -> Dict:
        with self._lock:
            cur = self._conn.execute("SELECT id, snapshot_json, created_at FROM snapshots WHERE id = ?", (snapshot_id,))
            row = cur.fetchone()
        if row is None:
            return {"error": f"no snapshot with id {snapshot_id}"}
        return self._row_to_dict(row)

    # -- diff -----------------------------------------------------------------
    @staticmethod
    def diff(snapshot_a: Dict, snapshot_b: Dict) -> Dict:
        """Shallow top-level key diff between two snapshot dicts: which
        top-level sections changed between a and b, and their before/after
        values. Sub-fields inside a changed section aren't diffed further -
        this flags *what* changed, callers can drill into the full values."""
        keys = set(snapshot_a.keys()) | set(snapshot_b.keys())
        changed = {}
        for key in keys:
            if key == "timestamp":
                continue
            before, after = snapshot_a.get(key), snapshot_b.get(key)
            if before != after:
                changed[key] = {"before": before, "after": after}
        return {
            "changed_sections": list(changed.keys()),
            "details": changed,
        }

    @staticmethod
    def _row_to_dict(row) -> Dict:
        try:
            snapshot = json.loads(row[1])
        except Exception:
            snapshot = {}
        return {"id": row[0], "snapshot": snapshot, "created_at": row[2]}


def get_context_snapshot() -> ContextSnapshot:
    """Process-wide ContextSnapshot singleton."""
    global _instance
    if _instance is None:
        with _instance_lock:
            if _instance is None:
                _instance = ContextSnapshot()
    return _instance
