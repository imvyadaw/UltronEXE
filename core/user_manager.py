"""
User Manager (Phase 21 - Unified Core Architecture)
====================================================
Ultron had no single notion of "who is talking to me" before this -
personalization/permissions were implicitly "whoever is at the
keyboard". This adds a lightweight multi-user identity layer: create a
user, track who's currently active, store per-user preferences and a
permission_level ("normal" | "elevated" | "admin") that
core/action_pipeline.py checks before running an elevated-permission
capability.

Storage: its own database/users.db via plain sqlite3, following the
same "several Phase 19.x subsystems write directly under database/"
pattern documented in database/database_manager.py, rather than
extending that module's fixed DB_FILES tuple for a Phase 21 addition.
Falls back to in-memory-only if the file can't be opened (read-only
filesystem, sandboxed run) so this module never blocks startup.
"""

import json
import sqlite3
import threading
import time
import uuid
from pathlib import Path
from typing import Dict, List, Optional

from core.logger import get_logger

logger = get_logger("ultron.user_manager")

DB_PATH = Path(__file__).resolve().parent.parent / "database" / "users.db"

VALID_PERMISSION_LEVELS = ("normal", "elevated", "admin")


class UserManager:
    """Process-wide user directory + active-session tracking. Use
    get_user_manager()."""

    def __init__(self, db_path: Path = DB_PATH):
        self._lock = threading.RLock()
        self._active_user_id: Optional[str] = None
        self._conn: Optional[sqlite3.Connection] = None
        self._memory_users: Dict[str, Dict] = {}
        self._open(db_path)

    def _open(self, db_path: Path) -> None:
        try:
            db_path.parent.mkdir(parents=True, exist_ok=True)
            self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id TEXT PRIMARY KEY,
                    username TEXT UNIQUE NOT NULL,
                    permission_level TEXT NOT NULL DEFAULT 'normal',
                    preferences TEXT NOT NULL DEFAULT '{}',
                    created_at REAL NOT NULL,
                    last_active_at REAL
                )
            """)
            self._conn.commit()
        except Exception as exc:
            logger.warning(f"user_manager: falling back to in-memory store: {exc}")
            self._conn = None

    # -- CRUD --------------------------------------------------------------
    def create_user(self, username: str, permission_level: str = "normal", preferences: Optional[Dict] = None) -> Dict:
        if permission_level not in VALID_PERMISSION_LEVELS:
            permission_level = "normal"
        user = {
            "id": str(uuid.uuid4()),
            "username": username,
            "permission_level": permission_level,
            "preferences": preferences or {},
            "created_at": time.time(),
            "last_active_at": None,
        }
        with self._lock:
            if self._conn:
                self._conn.execute(
                    "INSERT INTO users (id, username, permission_level, preferences, created_at) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (user["id"], username, permission_level, json.dumps(user["preferences"]), user["created_at"]),
                )
                self._conn.commit()
            else:
                self._memory_users[user["id"]] = user
        self._emit("user.created", user_id=user["id"], username=username)
        return user

    def get_user(self, user_id: str) -> Optional[Dict]:
        with self._lock:
            if self._conn:
                row = self._conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
                return self._row_to_dict(row) if row else None
            return self._memory_users.get(user_id)

    def get_user_by_username(self, username: str) -> Optional[Dict]:
        with self._lock:
            if self._conn:
                row = self._conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
                return self._row_to_dict(row) if row else None
            return next((u for u in self._memory_users.values() if u["username"] == username), None)

    def list_users(self) -> List[Dict]:
        with self._lock:
            if self._conn:
                rows = self._conn.execute("SELECT * FROM users ORDER BY created_at").fetchall()
                return [self._row_to_dict(r) for r in rows]
            return list(self._memory_users.values())

    def update_preferences(self, user_id: str, **preferences) -> Optional[Dict]:
        user = self.get_user(user_id)
        if not user:
            return None
        user["preferences"].update(preferences)
        with self._lock:
            if self._conn:
                self._conn.execute(
                    "UPDATE users SET preferences = ? WHERE id = ?", (json.dumps(user["preferences"]), user_id)
                )
                self._conn.commit()
            else:
                self._memory_users[user_id] = user
        return user

    # -- active session ----------------------------------------------------
    def set_active_user(self, user_id: str) -> Optional[Dict]:
        user = self.get_user(user_id)
        if not user:
            return None
        self._active_user_id = user_id
        user["last_active_at"] = time.time()
        with self._lock:
            if self._conn:
                self._conn.execute(
                    "UPDATE users SET last_active_at = ? WHERE id = ?", (user["last_active_at"], user_id)
                )
                self._conn.commit()
        self._emit("user.active_changed", user_id=user_id, username=user["username"])
        return user

    def get_active_user(self) -> Optional[Dict]:
        return self.get_user(self._active_user_id) if self._active_user_id else None

    def clear_active_user(self) -> None:
        self._active_user_id = None

    # -- helpers -----------------------------------------------------------
    def _row_to_dict(self, row: sqlite3.Row) -> Dict:
        d = dict(row)
        d["preferences"] = json.loads(d.get("preferences") or "{}")
        return d

    def _emit(self, event_name: str, **payload) -> None:
        try:
            from core.event_bus import get_event_bus

            get_event_bus().emit(event_name, **payload)
        except Exception:
            from core.error_trace import log_swallowed as _lsw

            _lsw("core.user_manager._emit")


_manager: Optional[UserManager] = None
_lock = threading.Lock()


def get_user_manager() -> UserManager:
    global _manager
    if _manager is None:
        with _lock:
            if _manager is None:
                _manager = UserManager()
    return _manager
