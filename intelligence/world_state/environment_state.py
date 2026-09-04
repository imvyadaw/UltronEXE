"""
Environment State (Phase 19.1 - World State)
==============================================
Ambient, slow-changing context around the machine rather than the
machine itself: time-of-day bucket, day of week, network reachability,
and a caller-supplied cache slot for things like weather (this module
makes no outbound network calls itself - it just stores whatever a
weather/location integration hands it, with a timestamp so callers
can tell when it's stale). Backed by a generic key/value table in
database/world_state.db so new ambient facts can be added later
without a schema change.
"""

import socket
import sqlite3
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

DB_PATH = Path(__file__).resolve().parent.parent.parent / "database" / "world_state.db"

_instance: Optional["EnvironmentState"] = None
_instance_lock = threading.Lock()


class EnvironmentState:
    """Ambient/environmental context: time, connectivity, and a generic
    key/value cache for things like weather or locale."""

    def __init__(self, db_path: Path = DB_PATH):
        self._db_path = db_path
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
        self._conn.execute("""CREATE TABLE IF NOT EXISTS environment_kv (
                key TEXT PRIMARY KEY,
                value TEXT,
                updated_at REAL
            )""")
        self._conn.commit()

    # -- time context (pure, no DB needed) ---------------------------------
    @staticmethod
    def get_time_context() -> Dict:
        """Current time bucket, day of week, and weekend flag - computed
        fresh each call, nothing to persist."""
        now = datetime.now()
        hour = now.hour
        if 5 <= hour < 12:
            bucket = "morning"
        elif 12 <= hour < 17:
            bucket = "afternoon"
        elif 17 <= hour < 21:
            bucket = "evening"
        else:
            bucket = "night"
        return {
            "time_of_day": bucket,
            "day_of_week": now.strftime("%A"),
            "is_weekend": now.weekday() >= 5,
            "iso_timestamp": now.isoformat(),
        }

    # -- connectivity ---------------------------------------------------------
    def check_connectivity(self, host: str = "8.8.8.8", port: int = 53, timeout: float = 2.0) -> Dict:
        """Real reachability probe (TCP connect, no data sent) - updates and
        returns the stored network_status/network_latency_ms."""
        start = time.time()
        try:
            sock = socket.create_connection((host, port), timeout=timeout)
            sock.close()
            latency_ms = round((time.time() - start) * 1000, 1)
            self.set("network_status", "online")
            self.set("network_latency_ms", latency_ms)
            return {"online": True, "latency_ms": latency_ms}
        except OSError as e:
            self.set("network_status", "offline")
            return {"online": False, "error": str(e)}

    # -- generic key/value ------------------------------------------------------
    def set(self, key: str, value: Any) -> Dict:
        """Store/overwrite one ambient fact (e.g. 'weather_cache',
        'timezone', 'locale'). Value is stored as its str() form."""
        if not key:
            return {"error": "key required"}
        with self._lock:
            self._conn.execute(
                """INSERT INTO environment_kv (key, value, updated_at) VALUES (?, ?, ?)
                   ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at""",
                (key, str(value), time.time()),
            )
            self._conn.commit()
        return {"success": True, "key": key}

    def get(self, key: str, default: Any = None) -> Any:
        with self._lock:
            cur = self._conn.execute("SELECT value FROM environment_kv WHERE key = ?", (key,))
            row = cur.fetchone()
        return row[0] if row else default

    def snapshot(self) -> Dict:
        """Everything currently tracked: computed time context plus every
        stored key/value fact."""
        with self._lock:
            cur = self._conn.execute("SELECT key, value, updated_at FROM environment_kv")
            rows = cur.fetchall()
        kv = {r[0]: {"value": r[1], "updated_at": r[2]} for r in rows}
        return {**self.get_time_context(), "facts": kv}


def get_environment_state() -> EnvironmentState:
    """Process-wide EnvironmentState singleton."""
    global _instance
    if _instance is None:
        with _instance_lock:
            if _instance is None:
                _instance = EnvironmentState()
    return _instance
