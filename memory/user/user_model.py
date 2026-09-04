"""User model (consolidated profile)
==================================
memory/long_term.py already stores raw (subject, predicate, value)
facts about the user, reinforced on repeat mention - "user, prefers,
dark_mode". That's the right place for one-off facts as they're
learned. What nothing in memory/ has is a *consolidated* view: one
row per named trait ("communication_style", "typical_work_hours",
"preferred_editor") holding Ultron's current best-known value for it,
a confidence score, how many times that's been reinforced, and -
unlike long_term's overwrite-on-restate - a kept history of what the
value used to be, since a trait can genuinely change over time ("used
to prefer dark mode, now prefers light") and that change is itself
worth remembering.

This is the layer learning/pattern_detector.py writes to once a
detected regularity is confident enough to call a trait of the user
rather than just a one-off pattern (memory/semantic/), and what
anything wanting "the current picture of this user" (a greeting,
a personalization pass, a dashboard) should read from instead of
re-deriving it from raw facts each time.
"""

import json
import sqlite3
import time
from pathlib import Path
from typing import Dict, Optional

DB_PATH = Path(__file__).resolve().parents[2] / "storage" / "sqlite" / "user_model.db"

DEFAULT_CONFIDENCE = 0.5
REINFORCE_STEP = 0.1
MAX_CONFIDENCE = 0.98
CHANGE_CONFIDENCE = (
    0.4  # a changed value starts lower than a first-ever value would, since it contradicts prior evidence
)


class UserModel:
    """One consolidated row per user trait, with confidence + a change history."""

    def __init__(self):
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
        self._conn.execute("""CREATE TABLE IF NOT EXISTS traits (
                dimension TEXT PRIMARY KEY,
                value TEXT,
                confidence REAL,
                evidence_count INTEGER,
                history TEXT,
                created_at REAL,
                updated_at REAL
            )""")
        self._conn.commit()

    def set_trait(
        self, dimension: str, value: str, confidence: float = DEFAULT_CONFIDENCE, evidence: Optional[str] = None
    ) -> Dict:
        """Record (or update) the current value for a trait dimension.
        Restating the same value reinforces confidence; a *different*
        value is recorded as a change - the old value moves into history
        rather than being silently lost, and the new value starts at a
        lower CHANGE_CONFIDENCE rather than inheriting the old
        confidence, since one contradicting observation shouldn't
        instantly outrank everything that came before it."""
        try:
            existing = self._get_row(dimension)
            now = time.time()
            if existing is None:
                self._conn.execute(
                    "INSERT INTO traits (dimension, value, confidence, evidence_count, history, "
                    "created_at, updated_at) VALUES (?, ?, ?, 1, ?, ?, ?)",
                    (dimension, value, min(confidence, MAX_CONFIDENCE), json.dumps([]), now, now),
                )
                self._conn.commit()
                return {"success": True, "dimension": dimension, "value": value, "changed": False, "new": True}

            if existing["value"] == value:
                return self.reinforce_trait(dimension, evidence=evidence)

            history = existing["history"]
            history.append(
                {
                    "value": existing["value"],
                    "confidence": existing["confidence"],
                    "replaced_at": now,
                    "evidence": evidence,
                }
            )
            self._conn.execute(
                "UPDATE traits SET value = ?, confidence = ?, evidence_count = 1, history = ?, updated_at = ? "
                "WHERE dimension = ?",
                (value, CHANGE_CONFIDENCE, json.dumps(history), now, dimension),
            )
            self._conn.commit()
            return {
                "success": True,
                "dimension": dimension,
                "value": value,
                "changed": True,
                "previous_value": history[-1]["value"],
            }
        except Exception as e:
            return {"error": str(e)}

    def reinforce_trait(self, dimension: str, evidence: Optional[str] = None) -> Dict:
        """The current value was observed again - raise confidence rather
        than treating it as a change."""
        try:
            existing = self._get_row(dimension)
            if existing is None:
                return {"error": f"No trait '{dimension}' set yet"}
            new_confidence = min(existing["confidence"] + REINFORCE_STEP, MAX_CONFIDENCE)
            self._conn.execute(
                "UPDATE traits SET confidence = ?, evidence_count = evidence_count + 1, updated_at = ? "
                "WHERE dimension = ?",
                (new_confidence, time.time(), dimension),
            )
            self._conn.commit()
            return {"success": True, "dimension": dimension, "confidence": new_confidence, "changed": False}
        except Exception as e:
            return {"error": str(e)}

    def get_trait(self, dimension: str) -> Dict:
        row = self._get_row(dimension)
        if row is None:
            return {"error": f"No trait '{dimension}' set yet"}
        return row

    def trait_history(self, dimension: str) -> Dict:
        row = self._get_row(dimension)
        if row is None:
            return {"error": f"No trait '{dimension}' set yet"}
        return {"dimension": dimension, "current_value": row["value"], "history": row["history"]}

    def all_traits(self, min_confidence: float = 0.0) -> Dict:
        """The full consolidated profile - what a personalization pass or
        dashboard should read."""
        try:
            cur = self._conn.cursor()
            cur.execute(
                "SELECT dimension, value, confidence, evidence_count, history, created_at, updated_at "
                "FROM traits WHERE confidence >= ? ORDER BY dimension",
                (min_confidence,),
            )
            traits = [self._row_to_dict(r) for r in cur.fetchall()]
            return {"count": len(traits), "traits": traits}
        except Exception as e:
            return {"error": str(e)}

    def search_traits(self, query: str) -> Dict:
        try:
            like = f"%{query.lower()}%"
            cur = self._conn.cursor()
            cur.execute(
                "SELECT dimension, value, confidence, evidence_count, history, created_at, updated_at "
                "FROM traits WHERE LOWER(dimension) LIKE ? OR LOWER(value) LIKE ?",
                (like, like),
            )
            traits = [self._row_to_dict(r) for r in cur.fetchall()]
            return {"query": query, "count": len(traits), "traits": traits}
        except Exception as e:
            return {"error": str(e)}

    def forget_trait(self, dimension: str) -> Dict:
        try:
            cur = self._conn.execute("DELETE FROM traits WHERE dimension = ?", (dimension,))
            self._conn.commit()
            if cur.rowcount == 0:
                return {"error": f"No trait '{dimension}' set yet"}
            return {"success": True, "forgotten": dimension}
        except Exception as e:
            return {"error": str(e)}

    def _get_row(self, dimension: str) -> Optional[Dict]:
        cur = self._conn.cursor()
        cur.execute(
            "SELECT dimension, value, confidence, evidence_count, history, created_at, updated_at "
            "FROM traits WHERE dimension = ?",
            (dimension,),
        )
        row = cur.fetchone()
        return self._row_to_dict(row) if row else None

    @staticmethod
    def _row_to_dict(row) -> Dict:
        dimension, value, confidence, evidence_count, history, created_at, updated_at = row
        try:
            history = json.loads(history or "[]")
        except json.JSONDecodeError:
            history = []
        return {
            "dimension": dimension,
            "value": value,
            "confidence": confidence,
            "evidence_count": evidence_count,
            "history": history,
            "created_at": created_at,
            "updated_at": updated_at,
        }


_user_model: Optional[UserModel] = None


def get_user_model() -> UserModel:
    """Process-wide singleton, matching memory.long_term.get_long_term_memory()."""
    global _user_model
    if _user_model is None:
        _user_model = UserModel()
    return _user_model
