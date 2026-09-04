"""
Device State (Phase 19.1 - World State)
=========================================
Registry of devices the world model knows about - peripherals, phones,
smart-home devices reachable via PHASE_18_9_SMART_DEVICES/DEVICES -
with a connection status and last-seen time, so context_snapshot.py
can answer "what's connected right now" without each subsystem
(voice, vision, smart-home) keeping its own separate bookkeeping.
This module only tracks status as reported to it; it doesn't perform
discovery or polling itself - callers (smart-home integration,
windows/ device checks, etc.) report in via register_device()/
update_status().
"""

import json
import sqlite3
import threading
import time
from pathlib import Path
from typing import Dict, List, Optional

DB_PATH = Path(__file__).resolve().parent.parent.parent / "database" / "world_state.db"

VALID_STATUSES = ("online", "offline", "unknown")

_instance: Optional["DeviceState"] = None
_instance_lock = threading.Lock()


class DeviceState:
    """Registry of known devices and their current connection status."""

    def __init__(self, db_path: Path = DB_PATH):
        self._db_path = db_path
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
        self._conn.execute("""CREATE TABLE IF NOT EXISTS devices (
                id TEXT PRIMARY KEY,
                name TEXT,
                device_type TEXT,
                connection TEXT,
                status TEXT,
                metadata TEXT,
                registered_at REAL,
                last_seen REAL
            )""")
        self._conn.commit()

    # -- writes -------------------------------------------------------------
    def register_device(
        self,
        device_id: str,
        name: str,
        device_type: str = "unknown",
        connection: str = "unknown",
        metadata: Optional[Dict] = None,
    ) -> Dict:
        """Add or overwrite a device record. Safe to call again for an
        already-known device (e.g. on reconnect) - it just updates the
        record and last_seen."""
        if not device_id or not name:
            return {"error": "device_id and name required"}
        now = time.time()
        with self._lock:
            self._conn.execute(
                """INSERT INTO devices (id, name, device_type, connection, status, metadata, registered_at, last_seen)
                   VALUES (?, ?, ?, ?, 'online', ?, ?, ?)
                   ON CONFLICT(id) DO UPDATE SET
                       name=excluded.name, device_type=excluded.device_type,
                       connection=excluded.connection, status='online',
                       metadata=excluded.metadata, last_seen=excluded.last_seen""",
                (device_id, name, device_type, connection, json.dumps(metadata or {}), now, now),
            )
            self._conn.commit()
        return self.get_device(device_id)

    def update_status(self, device_id: str, status: str, last_seen: Optional[float] = None) -> Dict:
        """Update a known device's connection status ('online'/'offline'/
        'unknown')."""
        if status not in VALID_STATUSES:
            return {"error": f"status must be one of {VALID_STATUSES}"}
        existing = self.get_device(device_id)
        if "error" in existing:
            return existing
        with self._lock:
            self._conn.execute(
                "UPDATE devices SET status = ?, last_seen = ? WHERE id = ?",
                (status, last_seen if last_seen is not None else time.time(), device_id),
            )
            self._conn.commit()
        return self.get_device(device_id)

    def remove_device(self, device_id: str) -> Dict:
        with self._lock:
            self._conn.execute("DELETE FROM devices WHERE id = ?", (device_id,))
            self._conn.commit()
        return {"success": True, "id": device_id}

    # -- reads ------------------------------------------------------------
    def get_device(self, device_id: str) -> Dict:
        with self._lock:
            cur = self._conn.execute(
                """SELECT id, name, device_type, connection, status, metadata, registered_at, last_seen
                   FROM devices WHERE id = ?""",
                (device_id,),
            )
            row = cur.fetchone()
        if row is None:
            return {"error": f"no device with id {device_id}"}
        return self._row_to_dict(row)

    def list_devices(self, status: Optional[str] = None, device_type: Optional[str] = None) -> List[Dict]:
        query = "SELECT id, name, device_type, connection, status, metadata, registered_at, last_seen FROM devices"
        clauses, params = [], []
        if status:
            clauses.append("status = ?")
            params.append(status)
        if device_type:
            clauses.append("device_type = ?")
            params.append(device_type)
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        query += " ORDER BY last_seen DESC"
        with self._lock:
            cur = self._conn.execute(query, params)
            rows = cur.fetchall()
        return [self._row_to_dict(r) for r in rows]

    def connected_devices(self) -> List[Dict]:
        """Shorthand for list_devices(status='online')."""
        return self.list_devices(status="online")

    @staticmethod
    def _row_to_dict(row) -> Dict:
        try:
            metadata = json.loads(row[5]) if row[5] else {}
        except Exception:
            metadata = {}
        return {
            "id": row[0],
            "name": row[1],
            "device_type": row[2],
            "connection": row[3],
            "status": row[4],
            "metadata": metadata,
            "registered_at": row[6],
            "last_seen": row[7],
        }


def get_device_state() -> DeviceState:
    """Process-wide DeviceState singleton."""
    global _instance
    if _instance is None:
        with _instance_lock:
            if _instance is None:
                _instance = DeviceState()
    return _instance
