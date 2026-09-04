"""
Knowledge OS Store (P3 - Unified Personal Knowledge OS)
========================================================
Sqlite CRUD for the OS's own `facts` table. This is deliberately a
thin, source-tagged fact ledger - NOT a replacement for
intelligence/knowledge_graph/ (entity/relation graph),
memory/semantic_memory.py, or memory/episodic_memory.py. Those keep
doing what they already do. This table exists because none of them
tag *which* subsystem a piece of knowledge came from, so there was no
single place to ask "what do I know about X, from everywhere, and how
fresh is it" - see knowledge_os_engine.py for the unification layer
that answers that.

Storage: database/knowledge_os.db, table facts.
"""

import sqlite3
import threading
import time
import uuid
from pathlib import Path
from typing import Dict, List, Optional

DB_PATH = Path(__file__).resolve().parent.parent.parent / "database" / "knowledge_os.db"

_instance: Optional["KnowledgeStore"] = None
_instance_lock = threading.Lock()


class KnowledgeStore:
    def __init__(self, db_path: Path = DB_PATH):
        self._db_path = db_path
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
        self._conn.execute("""CREATE TABLE IF NOT EXISTS facts (
                id TEXT PRIMARY KEY,
                subject TEXT,
                predicate TEXT,
                fact_text TEXT,
                source TEXT,
                confidence REAL,
                created_at REAL,
                updated_at REAL
            )""")
        self._conn.execute("CREATE INDEX IF NOT EXISTS idx_facts_subject ON facts(subject)")
        self._conn.commit()

    def upsert_fact(self, subject: str, predicate: str, fact_text: str, source: str, confidence: float) -> Dict:
        now = time.time()
        subject_n = subject.strip().lower()
        predicate_n = (predicate or "is").strip().lower()
        with self._lock:
            existing = self._conn.execute(
                "SELECT id FROM facts WHERE subject = ? AND predicate = ? AND source = ?",
                (subject_n, predicate_n, source),
            ).fetchone()
            if existing:
                fact_id = existing[0]
                self._conn.execute(
                    "UPDATE facts SET fact_text = ?, confidence = ?, updated_at = ? WHERE id = ?",
                    (fact_text, confidence, now, fact_id),
                )
            else:
                fact_id = str(uuid.uuid4())
                self._conn.execute(
                    """INSERT INTO facts (id, subject, predicate, fact_text, source, confidence,
                       created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (fact_id, subject_n, predicate_n, fact_text, source, confidence, now, now),
                )
            self._conn.commit()
        return self.get_fact(fact_id)

    def get_fact(self, fact_id: str) -> Optional[Dict]:
        row = self._conn.execute("SELECT * FROM facts WHERE id = ?", (fact_id,)).fetchone()
        return self._row_to_dict(row) if row else None

    def get_facts_for_subject(self, subject: str) -> List[Dict]:
        rows = self._conn.execute(
            "SELECT * FROM facts WHERE subject = ? ORDER BY updated_at DESC",
            (subject.strip().lower(),),
        ).fetchall()
        return [self._row_to_dict(r) for r in rows]

    def search_facts(self, query: str, limit: int = 20) -> List[Dict]:
        like = f"%{query.strip().lower()}%"
        rows = self._conn.execute(
            """SELECT * FROM facts WHERE subject LIKE ? OR fact_text LIKE ?
               ORDER BY updated_at DESC LIMIT ?""",
            (like, like, limit),
        ).fetchall()
        return [self._row_to_dict(r) for r in rows]

    def get_stale_facts(self, max_age_seconds: float) -> List[Dict]:
        cutoff = time.time() - max_age_seconds
        rows = self._conn.execute(
            "SELECT * FROM facts WHERE updated_at < ? ORDER BY updated_at ASC", (cutoff,)
        ).fetchall()
        return [self._row_to_dict(r) for r in rows]

    def get_all_subjects(self) -> List[str]:
        rows = self._conn.execute("SELECT DISTINCT subject FROM facts ORDER BY subject").fetchall()
        return [r[0] for r in rows]

    @staticmethod
    def _row_to_dict(row) -> Dict:
        return {
            "id": row[0],
            "subject": row[1],
            "predicate": row[2],
            "fact_text": row[3],
            "source": row[4],
            "confidence": row[5],
            "created_at": row[6],
            "updated_at": row[7],
        }


def get_knowledge_store() -> KnowledgeStore:
    global _instance
    if _instance is None:
        with _instance_lock:
            if _instance is None:
                _instance = KnowledgeStore()
    return _instance
