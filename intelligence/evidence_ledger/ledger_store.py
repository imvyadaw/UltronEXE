"""
Evidence Ledger Store (P2 - Evidence Ledger & Confidence Tracking)
===================================================================
reasoning/fact_checker.py + reasoning/evidence.py already produce a
confidence-labeled verdict for a claim - but that result is thrown
away the moment the call returns. Nothing remembers what Ultron
believed, how confident it was, or which sources it leaned on, so
there's no way to later ask "why did you say that" or to notice that
a particular source has quietly been wrong more often than right.

This is the persistence layer for that: every claim check gets logged
here, and once the real-world outcome becomes known (user corrects
Ultron, or confirms it was right), that outcome feeds back into a
running reliability score per evidence source.

Storage: database/evidence_ledger.db, tables evidence_entries /
source_reliability. Same sqlite-CRUD style as
intelligence/goal_manager/goal_store.py and
intelligence/mission_engine/mission_store.py on purpose.
"""

import json
import sqlite3
import threading
import time
import uuid
from pathlib import Path
from typing import Dict, List, Optional

DB_PATH = Path(__file__).resolve().parent.parent.parent / "database" / "evidence_ledger.db"

VALID_OUTCOMES = ("confirmed_true", "confirmed_false", "partially_true")

_instance: Optional["EvidenceLedgerStore"] = None
_instance_lock = threading.Lock()


class EvidenceLedgerStore:
    def __init__(self, db_path: Path = DB_PATH):
        self._db_path = db_path
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
        self._conn.execute("""CREATE TABLE IF NOT EXISTS evidence_entries (
                id TEXT PRIMARY KEY,
                claim TEXT,
                verdict TEXT,
                confidence REAL,
                evidence_json TEXT,
                context TEXT,
                created_at REAL,
                outcome TEXT,
                outcome_note TEXT,
                outcome_recorded_at REAL
            )""")
        self._conn.execute("""CREATE TABLE IF NOT EXISTS source_reliability (
                source TEXT PRIMARY KEY,
                times_cited INTEGER DEFAULT 0,
                times_correct INTEGER DEFAULT 0,
                times_wrong INTEGER DEFAULT 0,
                last_used_at REAL
            )""")
        self._conn.commit()

    # -- entries ----------------------------------------------------------
    def log_entry(
        self, claim: str, verdict: str, confidence: float, evidence: Optional[List[Dict]] = None, context: str = ""
    ) -> Dict:
        entry_id = str(uuid.uuid4())
        now = time.time()
        evidence = evidence or []
        with self._lock:
            self._conn.execute(
                """INSERT INTO evidence_entries
                   (id, claim, verdict, confidence, evidence_json, context, created_at,
                    outcome, outcome_note, outcome_recorded_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, NULL, NULL, NULL)""",
                (entry_id, claim, verdict, confidence, json.dumps(evidence), context, now),
            )
            for item in evidence:
                source = item.get("source", "unknown")
                self._conn.execute(
                    "INSERT INTO source_reliability (source, times_cited, last_used_at) VALUES (?, 1, ?) "
                    "ON CONFLICT(source) DO UPDATE SET times_cited = times_cited + 1, last_used_at = ?",
                    (source, now, now),
                )
            self._conn.commit()
        return self.get_entry(entry_id)

    def get_entry(self, entry_id: str) -> Optional[Dict]:
        row = self._conn.execute("SELECT * FROM evidence_entries WHERE id = ?", (entry_id,)).fetchone()
        return self._row_to_dict(row) if row else None

    def find_by_claim(self, claim_substring: str, limit: int = 5) -> List[Dict]:
        rows = self._conn.execute(
            "SELECT * FROM evidence_entries WHERE claim LIKE ? ORDER BY created_at DESC LIMIT ?",
            (f"%{claim_substring}%", limit),
        ).fetchall()
        return [self._row_to_dict(r) for r in rows]

    def get_recent(self, limit: int = 20) -> List[Dict]:
        rows = self._conn.execute(
            "SELECT * FROM evidence_entries ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
        return [self._row_to_dict(r) for r in rows]

    def record_outcome(self, entry_id: str, outcome: str, note: str = "") -> bool:
        if outcome not in VALID_OUTCOMES:
            return False
        entry = self.get_entry(entry_id)
        if not entry:
            return False
        now = time.time()
        with self._lock:
            self._conn.execute(
                "UPDATE evidence_entries SET outcome = ?, outcome_note = ?, outcome_recorded_at = ? WHERE id = ?",
                (outcome, note, now, entry_id),
            )
            correct = outcome in ("confirmed_true", "partially_true")
            for item in entry["evidence"]:
                source = item.get("source", "unknown")
                if correct:
                    self._conn.execute(
                        "UPDATE source_reliability SET times_correct = times_correct + 1 WHERE source = ?",
                        (source,),
                    )
                else:
                    self._conn.execute(
                        "UPDATE source_reliability SET times_wrong = times_wrong + 1 WHERE source = ?",
                        (source,),
                    )
            self._conn.commit()
        return True

    # -- source reliability ------------------------------------------------
    def get_source_stats(self, source: str) -> Dict:
        row = self._conn.execute(
            "SELECT times_cited, times_correct, times_wrong, last_used_at FROM source_reliability WHERE source = ?",
            (source,),
        ).fetchone()
        if row is None:
            return {
                "source": source,
                "times_cited": 0,
                "times_correct": 0,
                "times_wrong": 0,
                "reliability_score": 0.5,
                "last_used_at": None,
            }
        cited, correct, wrong, last_used = row
        judged = correct + wrong
        # Bayesian prior, same style as ai/tool_chain_optimizer.py's _score()
        # so both P1 and P2 scores mean the same thing to a caller.
        score = (correct + 1.0) / (judged + 2.0) if judged else 0.5
        return {
            "source": source,
            "times_cited": cited,
            "times_correct": correct,
            "times_wrong": wrong,
            "reliability_score": round(score, 4),
            "last_used_at": last_used,
        }

    def get_all_source_stats(self) -> List[Dict]:
        rows = self._conn.execute("SELECT source FROM source_reliability ORDER BY times_cited DESC").fetchall()
        return [self.get_source_stats(r[0]) for r in rows]

    # -- helpers ------------------------------------------------------
    @staticmethod
    def _row_to_dict(row) -> Dict:
        return {
            "id": row[0],
            "claim": row[1],
            "verdict": row[2],
            "confidence": row[3],
            "evidence": json.loads(row[4]) if row[4] else [],
            "context": row[5],
            "created_at": row[6],
            "outcome": row[7],
            "outcome_note": row[8],
            "outcome_recorded_at": row[9],
        }


def get_evidence_ledger_store() -> EvidenceLedgerStore:
    global _instance
    if _instance is None:
        with _instance_lock:
            if _instance is None:
                _instance = EvidenceLedgerStore()
    return _instance
