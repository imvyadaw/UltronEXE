"""SQLite storage
==============
Generic, reusable (category, key) -> value SQLite storage engine.
memory/long_term/long_term.py's LongTermMemory is built on top of this -
this module holds just the storage mechanics (connection, schema,
get/set/delete/search), so any other module that needs a durable
category/key store (a future skill's settings, a plugin's persisted
state, ...) can reuse it instead of hand-rolling another sqlite3 wrapper.

Kept separate from long_term.py deliberately: LongTermMemory's job is
*what* gets stored (user facts, with the specific store()/recall()/search()
vocabulary callers already use throughout the codebase); SQLiteStorage's
job is *how* it's stored (schema, connection lifecycle, SQL). Same split
as memory/vector_db/vector_store.py (search logic) vs a plain DB
connection would be, just made explicit as its own file per the Phase 3
layout.
"""

import sqlite3
import time
from pathlib import Path
from typing import Dict, List, Optional

DEFAULT_DB_PATH = Path(__file__).resolve().parents[2] / "storage" / "sqlite" / "long_term_memory.db"


class SQLiteStorage:
    """Durable (category, key) -> value storage, one row per pair,
    overwritten on re-store. Backs memory/long_term/long_term.py."""

    def __init__(self, db_path: Path = None, table: str = "facts"):
        self.db_path = db_path or DEFAULT_DB_PATH
        self.table = table
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self._conn.execute(f"""CREATE TABLE IF NOT EXISTS {self.table} (
                category TEXT,
                key TEXT,
                value TEXT,
                updated_at REAL,
                PRIMARY KEY (category, key)
            )""")
        self._conn.commit()

    def set(self, key: str, value: str, category: str = "general") -> Dict:
        try:
            self._conn.execute(
                f"INSERT OR REPLACE INTO {self.table} (category, key, value, updated_at) VALUES (?, ?, ?, ?)",
                (category, key, value, time.time()),
            )
            self._conn.commit()
            return {"success": True, "category": category, "key": key}
        except Exception as e:
            return {"error": str(e)}

    def get(self, key: str, category: str = "general") -> Optional[str]:
        cur = self._conn.cursor()
        cur.execute(f"SELECT value FROM {self.table} WHERE category=? AND key=?", (category, key))
        row = cur.fetchone()
        return row[0] if row else None

    def delete(self, key: str, category: str = "general") -> Dict:
        try:
            cur = self._conn.execute(f"DELETE FROM {self.table} WHERE category=? AND key=?", (category, key))
            self._conn.commit()
            return {"success": True, "deleted": cur.rowcount > 0}
        except Exception as e:
            return {"error": str(e)}

    def list_category(self, category: str = "general") -> List[Dict]:
        cur = self._conn.cursor()
        cur.execute(
            f"SELECT key, value, updated_at FROM {self.table} WHERE category=? ORDER BY updated_at DESC",
            (category,),
        )
        return [{"key": k, "value": v, "updated_at": ts} for k, v, ts in cur.fetchall()]

    def search(self, query: str) -> List[Dict]:
        """Substring match over both key and value, across all categories."""
        cur = self._conn.cursor()
        like = f"%{query}%"
        cur.execute(
            f"SELECT category, key, value, updated_at FROM {self.table} "
            f"WHERE key LIKE ? OR value LIKE ? ORDER BY updated_at DESC",
            (like, like),
        )
        return [{"category": c, "key": k, "value": v, "updated_at": ts} for c, k, v, ts in cur.fetchall()]

    def all_categories(self) -> List[str]:
        cur = self._conn.cursor()
        cur.execute(f"SELECT DISTINCT category FROM {self.table}")
        return [row[0] for row in cur.fetchall()]
