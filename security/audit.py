"""
Audit log
=========
Append-only record of security-relevant events: vault access, passphrase
changes, key rotation, failed auth attempts. Separate from core/logger.py
(general-purpose app logging) because this log has a different job -
answering "what security-sensitive things happened and when" - and
should never be silently rotated/truncated the way the general log is
(RotatingFileHandler in core/logger.py caps at 2MB / 3 backups).

Entries are immutable once written - there's no update/delete method by
design, matching how an audit trail is expected to behave.
"""

import json
import sqlite3
import time
from pathlib import Path
from typing import Dict, List, Optional

DB_PATH = Path(__file__).resolve().parents[1] / "storage" / "sqlite" / "audit_log.db"


class AuditLog:
    """Append-only log of security-relevant events."""

    def __init__(self):
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
        self._conn.execute("""CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_type TEXT NOT NULL,
                detail TEXT,
                success INTEGER,
                created_at REAL
            )""")
        self._conn.commit()

    def record(self, event_type: str, detail: Optional[Dict] = None, success: bool = True) -> Dict:
        """Log one event, e.g. record('vault_unlock', {'attempts': 1}, success=True)."""
        try:
            cur = self._conn.cursor()
            cur.execute(
                "INSERT INTO events (event_type, detail, success, created_at) VALUES (?, ?, ?, ?)",
                (event_type, json.dumps(detail or {}), int(success), time.time()),
            )
            self._conn.commit()
            return {"success": True, "id": cur.lastrowid}
        except Exception as e:
            return {"error": str(e)}

    def recent(self, limit: int = 50) -> Dict:
        try:
            cur = self._conn.cursor()
            cur.execute(
                "SELECT event_type, detail, success, created_at FROM events " "ORDER BY created_at DESC LIMIT ?",
                (limit,),
            )
            return {"events": self._rows_to_dicts(cur.fetchall())}
        except Exception as e:
            return {"error": str(e)}

    def by_type(self, event_type: str, limit: int = 50) -> Dict:
        try:
            cur = self._conn.cursor()
            cur.execute(
                "SELECT event_type, detail, success, created_at FROM events "
                "WHERE event_type = ? ORDER BY created_at DESC LIMIT ?",
                (event_type, limit),
            )
            return {"events": self._rows_to_dicts(cur.fetchall())}
        except Exception as e:
            return {"error": str(e)}

    def failed_events(self, limit: int = 50) -> Dict:
        """Just the failures - e.g. failed unlock attempts - for a quick
        'has anything suspicious happened' check."""
        try:
            cur = self._conn.cursor()
            cur.execute(
                "SELECT event_type, detail, success, created_at FROM events "
                "WHERE success = 0 ORDER BY created_at DESC LIMIT ?",
                (limit,),
            )
            return {"events": self._rows_to_dicts(cur.fetchall())}
        except Exception as e:
            return {"error": str(e)}

    def _rows_to_dicts(self, rows) -> List[Dict]:
        return [
            {
                "event_type": r[0],
                "detail": json.loads(r[1]) if r[1] else {},
                "success": bool(r[2]),
                "created_at": r[3],
            }
            for r in rows
        ]


_log: Optional[AuditLog] = None


def get_audit_log() -> AuditLog:
    global _log
    if _log is None:
        _log = AuditLog()
    return _log
