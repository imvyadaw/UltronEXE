"""
Retry Manager (Phase 19.5 - Self Healing)
=============================================
Tracks retry attempts per key (typically a failure_diagnoser.py
signature, or any caller-chosen string) with exponential backoff,
persisted so attempt counts survive a process restart instead of
resetting to zero every time ULTRON starts up. Only decides *whether*
and *when* a retry is allowed - it never performs the retried action
itself.

Storage: database/self_healing.db, table retry_state.
"""

import sqlite3
import threading
import time
from pathlib import Path
from typing import Dict, Optional

DB_PATH = Path(__file__).resolve().parent.parent.parent / "database" / "self_healing.db"

_instance: Optional["RetryManager"] = None
_instance_lock = threading.Lock()


class RetryManager:
    """Per-key retry attempt counter + exponential backoff gate."""

    def __init__(self, db_path: Path = DB_PATH):
        self._db_path = db_path
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
        self._conn.execute("""CREATE TABLE IF NOT EXISTS retry_state (
                key TEXT PRIMARY KEY,
                attempts INTEGER DEFAULT 0,
                next_allowed_at REAL,
                updated_at REAL
            )""")
        self._conn.commit()

    def get_state(self, key: str) -> Dict:
        with self._lock:
            cur = self._conn.execute(
                "SELECT key, attempts, next_allowed_at, updated_at FROM retry_state WHERE key = ?",
                (key,),
            )
            row = cur.fetchone()
        if row is None:
            return {"key": key, "attempts": 0, "next_allowed_at": 0.0, "updated_at": None}
        return {"key": row[0], "attempts": row[1], "next_allowed_at": row[2], "updated_at": row[3]}

    def should_retry(self, key: str, max_attempts: int = 3) -> bool:
        state = self.get_state(key)
        if state["attempts"] >= max_attempts:
            return False
        return time.time() >= (state["next_allowed_at"] or 0.0)

    def record_attempt(self, key: str, base_delay: float = 1.0, multiplier: float = 2.0) -> Dict:
        """Call after actually making an attempt (whether it failed or
        not) to advance the counter and push the next-allowed time
        further out. Delay grows as base_delay * multiplier**attempts."""
        state = self.get_state(key)
        attempts = state["attempts"] + 1
        delay = base_delay * (multiplier ** (attempts - 1))
        now = time.time()
        next_allowed_at = now + delay
        with self._lock:
            self._conn.execute(
                """INSERT INTO retry_state (key, attempts, next_allowed_at, updated_at)
                   VALUES (?, ?, ?, ?)
                   ON CONFLICT(key) DO UPDATE SET
                       attempts = excluded.attempts,
                       next_allowed_at = excluded.next_allowed_at,
                       updated_at = excluded.updated_at""",
                (key, attempts, next_allowed_at, now),
            )
            self._conn.commit()
        return {"key": key, "attempts": attempts, "next_allowed_at": next_allowed_at, "delay": delay}

    def reset(self, key: str) -> Dict:
        """Clear a key's retry history - call this once an attempt
        actually succeeds, so the next unrelated failure under the same
        key starts counting from zero again."""
        with self._lock:
            self._conn.execute("DELETE FROM retry_state WHERE key = ?", (key,))
            self._conn.commit()
        return {"success": True, "key": key}


def get_retry_manager() -> RetryManager:
    """Process-wide RetryManager singleton."""
    global _instance
    if _instance is None:
        with _instance_lock:
            if _instance is None:
                _instance = RetryManager()
    return _instance
