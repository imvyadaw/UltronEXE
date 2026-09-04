"""
Active Context (Phase 19.1 - World State)
==========================================
"What is being focused on right now" - active app/window, the task
(if any) that focus is tied to, and whether the user is actively
interacting or has gone idle. Complements core/context.py, which
already tracks active_app/current_directory/recent tool results for
the conversation layer; this module is the world-state layer's own
copy, persisted to database/world_state.db with a full transition
history (so "what were you focused on 10 minutes ago" is answerable),
rather than the flat single-value state core/context.py keeps.
Reading core/context.py's live value is optional and import-guarded -
this module works standalone.
"""

import sqlite3
import threading
import time
from pathlib import Path
from typing import Dict, List, Optional

DB_PATH = Path(__file__).resolve().parent.parent.parent / "database" / "world_state.db"

DEFAULT_IDLE_THRESHOLD_SECONDS = 300  # 5 minutes with no mark_interaction() -> idle

_instance: Optional["ActiveContext"] = None
_instance_lock = threading.Lock()


class ActiveContext:
    """Current focus state, with a persisted history of transitions."""

    def __init__(self, db_path: Path = DB_PATH):
        self._db_path = db_path
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
        self._conn.execute("""CREATE TABLE IF NOT EXISTS active_context_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                active_app TEXT,
                window_title TEXT,
                task_id TEXT,
                user_state TEXT,
                timestamp REAL
            )""")
        self._conn.commit()

        self._current: Dict = {
            "active_app": None,
            "window_title": None,
            "task_id": None,
            "user_state": "active",
            "last_interaction_at": time.time(),
            "focus_started_at": time.time(),
        }

    # -- updates --------------------------------------------------------
    def update(
        self,
        active_app: Optional[str] = None,
        window_title: Optional[str] = None,
        task_id: Optional[str] = None,
        user_state: Optional[str] = None,
    ) -> Dict:
        """Update whichever fields are given; unspecified fields are left
        as-is. Logs a transition row whenever active_app or task_id
        actually changes. Returns the new current() state."""
        with self._lock:
            changed_focus = (active_app is not None and active_app != self._current["active_app"]) or (
                task_id is not None and task_id != self._current["task_id"]
            )
            if active_app is not None:
                self._current["active_app"] = active_app
            if window_title is not None:
                self._current["window_title"] = window_title
            if task_id is not None:
                self._current["task_id"] = task_id
            if user_state is not None:
                self._current["user_state"] = user_state

            if changed_focus:
                self._current["focus_started_at"] = time.time()
                self._conn.execute(
                    """INSERT INTO active_context_log
                       (active_app, window_title, task_id, user_state, timestamp)
                       VALUES (?, ?, ?, ?, ?)""",
                    (
                        self._current["active_app"],
                        self._current["window_title"],
                        self._current["task_id"],
                        self._current["user_state"],
                        time.time(),
                    ),
                )
                self._conn.commit()

        return self.current()

    def mark_interaction(self) -> Dict:
        """Record that the user just did something (typed, clicked, spoke a
        command). Resets the idle clock and marks user_state='active'."""
        with self._lock:
            self._current["last_interaction_at"] = time.time()
            self._current["user_state"] = "active"
        return self.current()

    def check_idle(self, idle_threshold_seconds: int = DEFAULT_IDLE_THRESHOLD_SECONDS) -> bool:
        """If it's been longer than idle_threshold_seconds since the last
        mark_interaction(), flips user_state to 'idle' and returns True.
        Otherwise leaves state untouched and returns False."""
        with self._lock:
            elapsed = time.time() - self._current["last_interaction_at"]
            if elapsed > idle_threshold_seconds and self._current["user_state"] != "idle":
                self._current["user_state"] = "idle"
                return True
            return False

    # -- reads ------------------------------------------------------------
    def current(self) -> Dict:
        """Everything currently tracked about what's in focus."""
        with self._lock:
            snapshot = dict(self._current)
        snapshot["focus_duration_seconds"] = round(time.time() - snapshot["focus_started_at"], 2)
        snapshot["idle_seconds"] = round(time.time() - snapshot["last_interaction_at"], 2)
        return snapshot

    def history(self, limit: int = 50) -> List[Dict]:
        """Most recent focus transitions, newest first."""
        with self._lock:
            cur = self._conn.execute(
                """SELECT active_app, window_title, task_id, user_state, timestamp
                   FROM active_context_log ORDER BY timestamp DESC LIMIT ?""",
                (limit,),
            )
            rows = cur.fetchall()
        return [
            {"active_app": r[0], "window_title": r[1], "task_id": r[2], "user_state": r[3], "timestamp": r[4]}
            for r in rows
        ]

    def sync_from_conversation_context(self) -> Optional[Dict]:
        """Best-effort pull of active_app/current_directory from
        core.context's live ConversationContext, if the caller has one
        set up. Import-guarded: safe to call even if core/context.py's
        instance isn't wired up anywhere. Returns the updated current()
        state, or None if nothing was available to sync."""
        try:
            from core.context import ConversationContext  # noqa: F401
        except Exception:
            return None
        # core/context.py doesn't currently expose a module-level singleton
        # getter, so there's nothing live to pull from yet - this hook exists
        # for when one is added, without requiring a change to this module.
        return None


def get_active_context() -> ActiveContext:
    """Process-wide ActiveContext singleton."""
    global _instance
    if _instance is None:
        with _instance_lock:
            if _instance is None:
                _instance = ActiveContext()
    return _instance
