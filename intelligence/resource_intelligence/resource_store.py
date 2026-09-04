"""
Resource Intelligence Store (P3 - Resource-Aware Intelligence Engine)
======================================================================
Sqlite CRUD for empirical per-task-type resource cost history. Neither
monitoring/resource_monitor.py (point-in-time CPU/RAM/disk snapshots)
nor intelligence/predictive_preparation/resource_optimizer.py (an
in-memory-only allow/deny cooldown gate for background preloading)
remembers "how much does running task X actually tend to cost" across
restarts - this table is that missing memory.

Storage: database/resource_intelligence.db, table task_costs.
"""

import sqlite3
import threading
import time
from pathlib import Path
from typing import Dict, List, Optional

DB_PATH = Path(__file__).resolve().parent.parent.parent / "database" / "resource_intelligence.db"

_instance: Optional["ResourceStore"] = None
_instance_lock = threading.Lock()


class ResourceStore:
    def __init__(self, db_path: Path = DB_PATH):
        self._db_path = db_path
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
        self._conn.execute("""CREATE TABLE IF NOT EXISTS task_costs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_type TEXT,
                duration_ms REAL,
                cpu_delta REAL,
                mem_delta REAL,
                timestamp REAL
            )""")
        self._conn.execute("CREATE INDEX IF NOT EXISTS idx_task_costs_type ON task_costs(task_type)")
        self._conn.commit()

    def record(self, task_type: str, duration_ms: float, cpu_delta: float, mem_delta: float) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO task_costs (task_type, duration_ms, cpu_delta, mem_delta, timestamp) "
                "VALUES (?, ?, ?, ?, ?)",
                (task_type, duration_ms, cpu_delta, mem_delta, time.time()),
            )
            self._conn.commit()

    def get_profile(self, task_type: str, recent_n: int = 50) -> Dict:
        rows = self._conn.execute(
            "SELECT duration_ms, cpu_delta, mem_delta FROM task_costs "
            "WHERE task_type = ? ORDER BY timestamp DESC LIMIT ?",
            (task_type, recent_n),
        ).fetchall()
        if not rows:
            return {"task_type": task_type, "samples": 0}
        n = len(rows)
        avg_dur = sum(r[0] for r in rows) / n
        avg_cpu = sum(r[1] for r in rows) / n
        avg_mem = sum(r[2] for r in rows) / n
        return {
            "task_type": task_type,
            "samples": n,
            "avg_duration_ms": round(avg_dur, 1),
            "avg_cpu_delta": round(avg_cpu, 2),
            "avg_mem_delta": round(avg_mem, 2),
        }

    def get_all_task_types(self) -> List[str]:
        rows = self._conn.execute("SELECT DISTINCT task_type FROM task_costs").fetchall()
        return [r[0] for r in rows]

    def get_costliest_task_types(self, limit: int = 10) -> List[Dict]:
        types = self.get_all_task_types()
        profiles = [self.get_profile(t) for t in types]
        profiles.sort(key=lambda p: p.get("avg_duration_ms", 0), reverse=True)
        return profiles[:limit]


def get_resource_store() -> ResourceStore:
    global _instance
    if _instance is None:
        with _instance_lock:
            if _instance is None:
                _instance = ResourceStore()
    return _instance
