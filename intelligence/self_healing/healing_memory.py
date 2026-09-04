"""
Healing Memory (Phase 19.5 - Self Healing)
==============================================
Persistent memory of which recovery strategy actually worked the
last time a given failure signature (from failure_diagnoser.py) came
up, so strategy_generator.py can try the proven fix first instead of
working through its generic catalog from scratch every time. Purely
a record-keeper - it doesn't diagnose, generate, or execute
anything, just remembers outcomes and answers "what's worked before
for this".

Storage: database/self_healing.db, table healing_memory.
"""

import sqlite3
import threading
import time
from pathlib import Path
from typing import Dict, List, Optional

DB_PATH = Path(__file__).resolve().parent.parent.parent / "database" / "self_healing.db"

_instance: Optional["HealingMemory"] = None
_instance_lock = threading.Lock()


class HealingMemory:
    """signature -> best-known strategy, with running success/failure
    counts per (signature, strategy) pair."""

    def __init__(self, db_path: Path = DB_PATH):
        self._db_path = db_path
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
        self._conn.execute("""CREATE TABLE IF NOT EXISTS healing_memory (
                signature TEXT,
                strategy_name TEXT,
                category TEXT,
                action_name TEXT,
                success_count INTEGER DEFAULT 0,
                failure_count INTEGER DEFAULT 0,
                last_outcome TEXT,
                last_used_at REAL,
                PRIMARY KEY (signature, strategy_name)
            )""")
        self._conn.commit()

    def record_outcome(
        self, signature: str, strategy_name: str, success: bool, category: str = "", action_name: str = ""
    ) -> Dict:
        now = time.time()
        outcome = "success" if success else "failure"
        with self._lock:
            self._conn.execute(
                """INSERT INTO healing_memory
                   (signature, strategy_name, category, action_name,
                    success_count, failure_count, last_outcome, last_used_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(signature, strategy_name) DO UPDATE SET
                       success_count = success_count + excluded.success_count,
                       failure_count = failure_count + excluded.failure_count,
                       last_outcome = excluded.last_outcome,
                       last_used_at = excluded.last_used_at""",
                (
                    signature,
                    strategy_name,
                    category,
                    action_name,
                    1 if success else 0,
                    0 if success else 1,
                    outcome,
                    now,
                ),
            )
            self._conn.commit()
        return {"success": True}

    def best_strategy_for(self, signature: str) -> Optional[Dict]:
        """The strategy with the most recorded successes for this exact
        signature, ties broken by most recent use. None if nothing has
        ever succeeded for it (or nothing is recorded at all)."""
        with self._lock:
            cur = self._conn.execute(
                """SELECT strategy_name, success_count, failure_count, last_used_at
                   FROM healing_memory
                   WHERE signature = ? AND success_count > 0
                   ORDER BY success_count DESC, last_used_at DESC LIMIT 1""",
                (signature,),
            )
            row = cur.fetchone()
        if row is None:
            return None
        return {"strategy_name": row[0], "success_count": row[1], "failure_count": row[2], "last_used_at": row[3]}

    def get_stats(self, signature: str) -> List[Dict]:
        with self._lock:
            cur = self._conn.execute(
                """SELECT strategy_name, category, action_name, success_count,
                          failure_count, last_outcome, last_used_at
                   FROM healing_memory WHERE signature = ?
                   ORDER BY success_count DESC""",
                (signature,),
            )
            rows = cur.fetchall()
        return [
            {
                "strategy_name": r[0],
                "category": r[1],
                "action_name": r[2],
                "success_count": r[3],
                "failure_count": r[4],
                "last_outcome": r[5],
                "last_used_at": r[6],
            }
            for r in rows
        ]

    def forget(self, signature: str) -> Dict:
        with self._lock:
            self._conn.execute("DELETE FROM healing_memory WHERE signature = ?", (signature,))
            self._conn.commit()
        return {"success": True, "signature": signature}


def get_healing_memory() -> HealingMemory:
    """Process-wide HealingMemory singleton."""
    global _instance
    if _instance is None:
        with _instance_lock:
            if _instance is None:
                _instance = HealingMemory()
    return _instance
