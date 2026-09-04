"""
Fallback Chain (Phase 19.5 - Self Healing)
==============================================
Registry of ordered alternate actions to fall back to when an
action's own retries/strategies are exhausted - e.g. action
"send_via_primary_api" might register a fallback chain of
["send_via_secondary_api", "queue_for_later", "notify_user"]. This
is a different axis from strategy_generator.py: strategies are ways
of retrying the *same* action, a fallback chain is a sequence of
*different* actions to try instead once that's given up. Purely a
registry + "what's the next untried one" - it never executes
anything itself.

Storage: database/self_healing.db, table fallback_chains.
"""

import json
import sqlite3
import threading
import time
from pathlib import Path
from typing import Dict, List, Optional

DB_PATH = Path(__file__).resolve().parent.parent.parent / "database" / "self_healing.db"

_instance: Optional["FallbackChain"] = None
_instance_lock = threading.Lock()


class FallbackChain:
    """action_name -> ordered list of fallback action names."""

    def __init__(self, db_path: Path = DB_PATH):
        self._db_path = db_path
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
        self._conn.execute("""CREATE TABLE IF NOT EXISTS fallback_chains (
                action_name TEXT PRIMARY KEY,
                fallback_json TEXT,
                updated_at REAL
            )""")
        self._conn.commit()

    def register_chain(self, action_name: str, fallback_actions: List[str]) -> Dict:
        now = time.time()
        with self._lock:
            self._conn.execute(
                """INSERT INTO fallback_chains (action_name, fallback_json, updated_at)
                   VALUES (?, ?, ?)
                   ON CONFLICT(action_name) DO UPDATE SET
                       fallback_json = excluded.fallback_json, updated_at = excluded.updated_at""",
                (action_name, json.dumps(fallback_actions), now),
            )
            self._conn.commit()
        return self.get_chain(action_name)

    def get_chain(self, action_name: str) -> Dict:
        with self._lock:
            cur = self._conn.execute(
                "SELECT action_name, fallback_json, updated_at FROM fallback_chains WHERE action_name = ?",
                (action_name,),
            )
            row = cur.fetchone()
        if row is None:
            return {"action_name": action_name, "fallback_actions": [], "updated_at": None}
        try:
            fallback_actions = json.loads(row[1]) if row[1] else []
        except Exception:
            fallback_actions = []
        return {"action_name": row[0], "fallback_actions": fallback_actions, "updated_at": row[2]}

    def get_next_fallback(self, action_name: str, attempted: Optional[List[str]] = None) -> Optional[str]:
        """The first fallback action registered for action_name that
        isn't already in `attempted`. None if the chain is exhausted or
        was never registered."""
        attempted = set(attempted or [])
        chain = self.get_chain(action_name)
        for candidate in chain["fallback_actions"]:
            if candidate not in attempted:
                return candidate
        return None

    def delete_chain(self, action_name: str) -> Dict:
        with self._lock:
            self._conn.execute("DELETE FROM fallback_chains WHERE action_name = ?", (action_name,))
            self._conn.commit()
        return {"success": True, "action_name": action_name}


def get_fallback_chain() -> FallbackChain:
    """Process-wide FallbackChain singleton."""
    global _instance
    if _instance is None:
        with _instance_lock:
            if _instance is None:
                _instance = FallbackChain()
    return _instance
