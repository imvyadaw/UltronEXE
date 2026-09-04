"""
Pending Actions (Phase 30 - Approval)
======================================
Lowest layer of the approval/ package: plain sqlite CRUD for actions
that are waiting on a yes/no decision from the user before
execution/action_manager.py is allowed to run them.

Relationship to core/permissions.py's PermissionGate: PermissionGate
only answers "does this tool name require confirmation" from a static
set - it has nowhere to put an action while it waits, and no record of
what was asked, when, or how it was resolved. This module is that
missing queue: every action approval_manager.py decides needs a human
decision gets a row here (status "pending"), and stays queryable until
approve()/deny() (or a caller's timeout policy) resolves it.

Storage: database/approvals.db, table pending_actions. Same
conventions as intelligence/goal_manager/goal_store.py (singleton via
get_pending_actions(), threading.Lock around the connection, WAL not
needed at this volume).
"""

import json
import sqlite3
import threading
import time
import uuid
from pathlib import Path
from typing import Dict, List, Optional

from core.logger import get_logger

logger = get_logger("ultron.approval.pending_actions")

DB_PATH = Path(__file__).resolve().parent.parent / "database" / "approvals.db"

VALID_STATUSES = ("pending", "approved", "denied", "expired", "auto_approved")


class PendingActions:
    """Persistence for actions awaiting approval. Every status change
    is a plain UPDATE - callers wanting history should read
    action_manager.py's own logging, this table only reflects current
    state per action_id."""

    def __init__(self, db_path: Path = DB_PATH):
        self._db_path = db_path
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._init_db()

    def _init_db(self):
        with self._lock, sqlite3.connect(self._db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS pending_actions (
                    action_id TEXT PRIMARY KEY,
                    action_name TEXT NOT NULL,
                    arguments TEXT NOT NULL,
                    reason TEXT,
                    risk_level TEXT NOT NULL DEFAULT 'unknown',
                    status TEXT NOT NULL DEFAULT 'pending',
                    requested_by TEXT,
                    created_at REAL NOT NULL,
                    resolved_at REAL
                )
            """)
            conn.commit()

    def create(
        self,
        action_name: str,
        arguments: Dict,
        reason: str = "",
        risk_level: str = "unknown",
        requested_by: Optional[str] = None,
    ) -> str:
        action_id = str(uuid.uuid4())
        with self._lock, sqlite3.connect(self._db_path) as conn:
            conn.execute(
                "INSERT INTO pending_actions "
                "(action_id, action_name, arguments, reason, risk_level, status, requested_by, created_at) "
                "VALUES (?, ?, ?, ?, ?, 'pending', ?, ?)",
                (action_id, action_name, json.dumps(arguments), reason, risk_level, requested_by, time.time()),
            )
            conn.commit()
        logger.info(f"Queued approval request {action_id} for '{action_name}' (risk={risk_level})")
        return action_id

    def resolve(self, action_id: str, status: str) -> bool:
        if status not in VALID_STATUSES:
            raise ValueError(f"invalid status '{status}'")
        with self._lock, sqlite3.connect(self._db_path) as conn:
            cur = conn.execute(
                "UPDATE pending_actions SET status = ?, resolved_at = ? " "WHERE action_id = ? AND status = 'pending'",
                (status, time.time(), action_id),
            )
            conn.commit()
            return cur.rowcount > 0

    def get(self, action_id: str) -> Optional[Dict]:
        with self._lock, sqlite3.connect(self._db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute("SELECT * FROM pending_actions WHERE action_id = ?", (action_id,)).fetchone()
            return self._row_to_dict(row) if row else None

    def list_pending(self) -> List[Dict]:
        with self._lock, sqlite3.connect(self._db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM pending_actions WHERE status = 'pending' ORDER BY created_at ASC"
            ).fetchall()
            return [self._row_to_dict(r) for r in rows]

    def expire_older_than(self, seconds: float) -> int:
        """Sweep stale pending requests (no answer within `seconds`)
        to 'expired' so action_manager.py stops waiting on them."""
        cutoff = time.time() - seconds
        with self._lock, sqlite3.connect(self._db_path) as conn:
            cur = conn.execute(
                "UPDATE pending_actions SET status = 'expired', resolved_at = ? "
                "WHERE status = 'pending' AND created_at < ?",
                (time.time(), cutoff),
            )
            conn.commit()
            return cur.rowcount

    @staticmethod
    def _row_to_dict(row: sqlite3.Row) -> Dict:
        d = dict(row)
        d["arguments"] = json.loads(d["arguments"])
        return d


_instance: Optional[PendingActions] = None
_instance_lock = threading.Lock()


def get_pending_actions() -> PendingActions:
    global _instance
    if _instance is None:
        with _instance_lock:
            if _instance is None:
                _instance = PendingActions()
    return _instance
