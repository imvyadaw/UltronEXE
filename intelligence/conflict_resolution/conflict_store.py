"""
Conflict Resolution Store (P4 - Conflict Resolution Engine)
=============================================================
Sqlite CRUD for logged contradictions between two sources' claims
about the same subject. Nothing in the existing build currently
notices when two sources disagree - intelligence/evidence_ledger/
(P2) tracks per-source reliability but not cross-source disagreement,
and intelligence/knowledge_os/ (P3) tags facts by source but doesn't
compare them. This table is where a detected disagreement is
recorded and, once resolved, kept as an auditable decision trail.

Storage: database/conflict_resolution.db, table conflicts.
"""

import sqlite3
import threading
import time
import uuid
from pathlib import Path
from typing import Dict, List, Optional

DB_PATH = Path(__file__).resolve().parent.parent.parent / "database" / "conflict_resolution.db"

_instance: Optional["ConflictStore"] = None
_instance_lock = threading.Lock()


class ConflictStore:
    def __init__(self, db_path: Path = DB_PATH):
        self._db_path = db_path
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
        self._conn.execute("""CREATE TABLE IF NOT EXISTS conflicts (
                id TEXT PRIMARY KEY,
                subject TEXT,
                claim_a TEXT,
                source_a TEXT,
                claim_b TEXT,
                source_b TEXT,
                status TEXT,
                resolution TEXT,
                resolved_source TEXT,
                note TEXT,
                created_at REAL,
                resolved_at REAL
            )""")
        self._conn.commit()

    def log_conflict(self, subject: str, claim_a: str, source_a: str, claim_b: str, source_b: str) -> Dict:
        conflict_id = str(uuid.uuid4())
        now = time.time()
        with self._lock:
            self._conn.execute(
                """INSERT INTO conflicts (id, subject, claim_a, source_a, claim_b, source_b,
                   status, resolution, resolved_source, note, created_at, resolved_at)
                   VALUES (?, ?, ?, ?, ?, ?, 'open', NULL, NULL, NULL, ?, NULL)""",
                (conflict_id, subject, claim_a, source_a, claim_b, source_b, now),
            )
            self._conn.commit()
        return self.get_conflict(conflict_id)

    def get_conflict(self, conflict_id: str) -> Optional[Dict]:
        row = self._conn.execute("SELECT * FROM conflicts WHERE id = ?", (conflict_id,)).fetchone()
        return self._row_to_dict(row) if row else None

    def get_open_conflicts(self, subject: Optional[str] = None) -> List[Dict]:
        if subject:
            rows = self._conn.execute(
                "SELECT * FROM conflicts WHERE status = 'open' AND subject = ? ORDER BY created_at DESC",
                (subject,),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM conflicts WHERE status = 'open' ORDER BY created_at DESC"
            ).fetchall()
        return [self._row_to_dict(r) for r in rows]

    def resolve(self, conflict_id: str, resolution: str, resolved_source: str, note: str = "") -> bool:
        conflict = self.get_conflict(conflict_id)
        if not conflict:
            return False
        with self._lock:
            self._conn.execute(
                "UPDATE conflicts SET status = 'resolved', resolution = ?, resolved_source = ?, "
                "note = ?, resolved_at = ? WHERE id = ?",
                (resolution, resolved_source, note, time.time(), conflict_id),
            )
            self._conn.commit()
        return True

    def get_recent(self, limit: int = 20) -> List[Dict]:
        rows = self._conn.execute("SELECT * FROM conflicts ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
        return [self._row_to_dict(r) for r in rows]

    @staticmethod
    def _row_to_dict(row) -> Dict:
        return {
            "id": row[0],
            "subject": row[1],
            "claim_a": row[2],
            "source_a": row[3],
            "claim_b": row[4],
            "source_b": row[5],
            "status": row[6],
            "resolution": row[7],
            "resolved_source": row[8],
            "note": row[9],
            "created_at": row[10],
            "resolved_at": row[11],
        }


def get_conflict_store() -> ConflictStore:
    global _instance
    if _instance is None:
        with _instance_lock:
            if _instance is None:
                _instance = ConflictStore()
    return _instance
