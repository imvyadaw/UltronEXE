"""
Long-Term Memory
================
memory/emotional_memory.py already owns mood - personality.py reads
its mood_trend() directly and nothing here touches that table or that
category. What memory/ never grew was a general-purpose place for
plain facts ("prefers dark mode", "calls the work laptop 'the
beast'") that aren't mood and aren't a person/place/habit either -
those three get their own modules (face_memory/place_memory/
habit_memory) for exactly the same reason emotional_memory got its
own table instead of being a generic key-value blob. long_term.py is
that remaining general case.

Facts are (subject, predicate, value) triples - "user, prefers,
dark_mode" - with a confidence score that starts moderate and is
reinforced (not reset) each time the same triple is restated, so a
fact mentioned five times outranks one mentioned once without either
one being deleted to make room. Nothing here decays or auto-forgets -
that would make this indistinguishable from short_term.py. Deletion
is deliberately not exposed as a casual public method; the only
supported path is forget.py's forget_fact(), so every deletion goes
through one auditable place instead of being scattered across
whichever module happens to hold the data (see forget.py's own
docstring for why that matters).
"""

import sqlite3
import time
from pathlib import Path
from typing import Dict, List, Optional

DB_PATH = Path(__file__).resolve().parents[1] / "storage" / "sqlite" / "long_term_memory.db"

DEFAULT_CONFIDENCE = 0.6
REINFORCE_STEP = 0.1
MAX_CONFIDENCE = 0.99


class LongTermMemory:
    """Durable (subject, predicate, value) fact store. Use get_long_term_memory()."""

    def __init__(self):
        self._db_ok = True
        try:
            DB_PATH.parent.mkdir(parents=True, exist_ok=True)
            self._conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
            self._conn.execute("""CREATE TABLE IF NOT EXISTS facts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    subject TEXT, predicate TEXT, value TEXT,
                    confidence REAL, source TEXT,
                    first_seen REAL, last_seen REAL, times_seen INTEGER,
                    UNIQUE(subject, predicate, value)
                )""")
            self._conn.commit()
        except Exception:
            self._db_ok = False
            self._fallback: List[Dict] = []  # in-memory only, lost on restart

    def remember_fact(
        self,
        subject: str,
        predicate: str,
        value: str,
        source: str = "conversation",
        confidence: float = DEFAULT_CONFIDENCE,
    ) -> Dict:
        """Store or reinforce a fact. Restating the same (subject,
        predicate, value) reinforces confidence instead of duplicating
        the row - see REINFORCE_STEP."""
        now = time.time()
        if not self._db_ok:
            for f in self._fallback:
                if (f["subject"], f["predicate"], f["value"]) == (subject, predicate, value):
                    f["confidence"] = min(MAX_CONFIDENCE, f["confidence"] + REINFORCE_STEP)
                    f["times_seen"] += 1
                    f["last_seen"] = now
                    return f
            entry = {
                "subject": subject,
                "predicate": predicate,
                "value": value,
                "confidence": confidence,
                "source": source,
                "first_seen": now,
                "last_seen": now,
                "times_seen": 1,
            }
            self._fallback.append(entry)
            return entry

        cur = self._conn.cursor()
        cur.execute(
            "SELECT confidence, times_seen FROM facts WHERE subject=? AND predicate=? AND value=?",
            (subject, predicate, value),
        )
        row = cur.fetchone()
        if row:
            new_confidence = min(MAX_CONFIDENCE, row[0] + REINFORCE_STEP)
            new_times = row[1] + 1
            self._conn.execute(
                "UPDATE facts SET confidence=?, times_seen=?, last_seen=? "
                "WHERE subject=? AND predicate=? AND value=?",
                (new_confidence, new_times, now, subject, predicate, value),
            )
        else:
            new_confidence, new_times = confidence, 1
            self._conn.execute(
                "INSERT INTO facts (subject, predicate, value, confidence, source, "
                "first_seen, last_seen, times_seen) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (subject, predicate, value, confidence, source, now, now, 1),
            )
        self._conn.commit()
        return {
            "subject": subject,
            "predicate": predicate,
            "value": value,
            "confidence": new_confidence,
            "source": source,
            "times_seen": new_times,
        }

    def facts_about(self, subject: str, min_confidence: float = 0.0) -> List[Dict]:
        if not self._db_ok:
            return [f for f in self._fallback if f["subject"] == subject and f["confidence"] >= min_confidence]
        cur = self._conn.cursor()
        cur.execute(
            "SELECT subject, predicate, value, confidence, source, times_seen, last_seen "
            "FROM facts WHERE subject=? AND confidence>=? ORDER BY confidence DESC",
            (subject, min_confidence),
        )
        cols = ["subject", "predicate", "value", "confidence", "source", "times_seen", "last_seen"]
        return [dict(zip(cols, row)) for row in cur.fetchall()]

    def all_facts(self, min_confidence: float = 0.0) -> List[Dict]:
        if not self._db_ok:
            return [f for f in self._fallback if f["confidence"] >= min_confidence]
        cur = self._conn.cursor()
        cur.execute(
            "SELECT subject, predicate, value, confidence, source, times_seen, last_seen "
            "FROM facts WHERE confidence>=? ORDER BY last_seen DESC",
            (min_confidence,),
        )
        cols = ["subject", "predicate", "value", "confidence", "source", "times_seen", "last_seen"]
        return [dict(zip(cols, row)) for row in cur.fetchall()]

    # -- deletion primitive - forget.py is the only intended caller -----
    def _delete_fact(self, subject: str, predicate: Optional[str] = None) -> int:
        """Not part of the public API on purpose (leading underscore) -
        forget.py wraps this so every deletion is logged in one place.
        Returns the number of rows removed."""
        if not self._db_ok:
            before = len(self._fallback)
            self._fallback = [
                f
                for f in self._fallback
                if not (f["subject"] == subject and (predicate is None or f["predicate"] == predicate))
            ]
            return before - len(self._fallback)
        cur = self._conn.cursor()
        if predicate is None:
            cur.execute("DELETE FROM facts WHERE subject=?", (subject,))
        else:
            cur.execute("DELETE FROM facts WHERE subject=? AND predicate=?", (subject, predicate))
        self._conn.commit()
        return cur.rowcount


_long_term: Optional[LongTermMemory] = None


def get_long_term_memory() -> LongTermMemory:
    global _long_term
    if _long_term is None:
        _long_term = LongTermMemory()
    return _long_term
