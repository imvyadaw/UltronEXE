"""
PC State (Phase 19.1 - World State)
====================================
Point-in-time and historical snapshots of the machine Ultron runs on:
OS/host identity, CPU/RAM/disk load, and battery (if present).
Overlaps in raw metrics with monitoring/resource_monitor.py, but
where that module keeps an in-memory rolling window for "is the PC
loaded right now" checks, this one persists every capture to
database/world_state.db so world_state_manager.py and
context_snapshot.py can answer "what was the machine doing at time T"
later, alongside the rest of the world model. psutil is already a
hard dependency of the project (see monitoring/resource_monitor.py).
"""

import platform
import socket
import sqlite3
import threading
import time
from pathlib import Path
from typing import Dict, List, Optional

import psutil

DB_PATH = Path(__file__).resolve().parent.parent.parent / "database" / "world_state.db"

_instance: Optional["PCState"] = None
_instance_lock = threading.Lock()


class PCState:
    """Captures and persists machine-level state readings."""

    def __init__(self, db_path: Path = DB_PATH):
        self._db_path = db_path
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
        self._conn.execute("""CREATE TABLE IF NOT EXISTS pc_state_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                hostname TEXT,
                os_name TEXT,
                os_version TEXT,
                cpu_percent REAL,
                memory_percent REAL,
                disk_percent REAL,
                battery_percent REAL,
                battery_plugged INTEGER,
                uptime_seconds REAL,
                timestamp REAL
            )""")
        self._conn.commit()

    # -- capture ----------------------------------------------------------
    def capture(self, disk_path: Optional[str] = None) -> Dict:
        """Read current machine state via psutil/platform and persist it.
        Returns the captured reading, or {"error": ...} on failure."""
        try:
            disk_path = disk_path or str(Path.home().anchor or "/")
            cpu_percent = psutil.cpu_percent(interval=0.2)
            memory = psutil.virtual_memory()
            disk = psutil.disk_usage(disk_path)

            battery_percent = None
            battery_plugged = None
            battery = getattr(psutil, "sensors_battery", lambda: None)()
            if battery is not None:
                battery_percent = battery.percent
                battery_plugged = bool(battery.power_plugged)

            reading = {
                "hostname": socket.gethostname(),
                "os_name": platform.system(),
                "os_version": platform.version(),
                "cpu_percent": cpu_percent,
                "memory_percent": memory.percent,
                "disk_percent": disk.percent,
                "battery_percent": battery_percent,
                "battery_plugged": battery_plugged,
                "uptime_seconds": round(time.time() - psutil.boot_time(), 2),
                "timestamp": time.time(),
            }

            with self._lock:
                self._conn.execute(
                    """INSERT INTO pc_state_log
                       (hostname, os_name, os_version, cpu_percent, memory_percent,
                        disk_percent, battery_percent, battery_plugged, uptime_seconds, timestamp)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        reading["hostname"],
                        reading["os_name"],
                        reading["os_version"],
                        reading["cpu_percent"],
                        reading["memory_percent"],
                        reading["disk_percent"],
                        reading["battery_percent"],
                        None if battery_plugged is None else int(battery_plugged),
                        reading["uptime_seconds"],
                        reading["timestamp"],
                    ),
                )
                self._conn.commit()

            return {"success": True, **reading}
        except Exception as e:
            return {"error": str(e)}

    # -- reads --------------------------------------------------------------
    def current(self) -> Dict:
        """Most recent captured reading, or a fresh capture() if none exist yet."""
        row = self._latest_row()
        if row is None:
            return self.capture()
        return self._row_to_dict(row)

    def history(self, limit: int = 50) -> List[Dict]:
        """Most recent readings, newest first."""
        with self._lock:
            cur = self._conn.execute(
                """SELECT hostname, os_name, os_version, cpu_percent, memory_percent,
                          disk_percent, battery_percent, battery_plugged, uptime_seconds, timestamp
                   FROM pc_state_log ORDER BY timestamp DESC LIMIT ?""",
                (limit,),
            )
            rows = cur.fetchall()
        return [self._row_to_dict(r) for r in rows]

    def _latest_row(self):
        with self._lock:
            cur = self._conn.execute("""SELECT hostname, os_name, os_version, cpu_percent, memory_percent,
                          disk_percent, battery_percent, battery_plugged, uptime_seconds, timestamp
                   FROM pc_state_log ORDER BY timestamp DESC LIMIT 1""")
            return cur.fetchone()

    @staticmethod
    def _row_to_dict(row) -> Dict:
        return {
            "hostname": row[0],
            "os_name": row[1],
            "os_version": row[2],
            "cpu_percent": row[3],
            "memory_percent": row[4],
            "disk_percent": row[5],
            "battery_percent": row[6],
            "battery_plugged": None if row[7] is None else bool(row[7]),
            "uptime_seconds": row[8],
            "timestamp": row[9],
        }


def get_pc_state() -> PCState:
    """Process-wide PCState singleton."""
    global _instance
    if _instance is None:
        with _instance_lock:
            if _instance is None:
                _instance = PCState()
    return _instance
