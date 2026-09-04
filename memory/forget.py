"""
Forget
======
Every other module in MEMORY/ exposes its deletion as a private,
underscore-prefixed primitive (_delete_person, _delete_place,
_delete_fact, _delete_action) instead of a public method - on purpose.
Deletion is the one operation in this whole memory system that must
never be silent, never be scattered across five different call sites,
and never partially cascade without a record of what happened. This
module is the single place that's allowed to call those primitives,
and every call is written to its own audit trail (storage/sqlite/
forget_audit.db) *before* the deletion runs - so even if the deletion
itself fails partway, there's a record that it was attempted.

Cascades are explicit, not automatic: forgetting a person also removes
any long_term facts whose subject is that name (people talk about
people - "user's sister likes tea" - and a stray fact surviving a
"forget my sister" request would defeat the point of asking). Forgetting
a place or a habit does not cascade into long_term by default, since
those subjects are far more likely to be shared/generic (e.g. "office"
as both a place name and a fact subject about work) - callers who do
want that can pass cascade_facts=True.

forget_everything() is deliberately the most guarded function here: it
requires confirm=True, still writes the audit entry first, and still
only wipes MEMORY/ - it has no reach into memory/emotional_memory.py or
anything from Phase 1-17, matching this whole phase's "purely
additive, nothing else depends on it" guarantee in reverse: this
module can't un-additive anything outside itself either.
"""

import sqlite3
import time
from pathlib import Path
from typing import Dict, List, Optional

from memory.short_term import get_short_term_memory
from memory.long_term import get_long_term_memory
from memory.face_memory import get_face_memory
from memory.place_memory import get_place_memory
from memory.habit_memory import get_habit_memory

DB_PATH = Path(__file__).resolve().parents[1] / "storage" / "sqlite" / "forget_audit.db"


class Forget:
    """The only supported way to delete anything from MEMORY/. Use get_forgetter()."""

    def __init__(self):
        self._db_ok = True
        try:
            DB_PATH.parent.mkdir(parents=True, exist_ok=True)
            self._conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
            self._conn.execute("""CREATE TABLE IF NOT EXISTS audit (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    operation TEXT, target TEXT, detail TEXT, logged_at REAL
                )""")
            self._conn.commit()
        except Exception:
            self._db_ok = False
            self._fallback_audit: List[Dict] = []

    def _record(self, operation: str, target: str, detail: str = "") -> None:
        now = time.time()
        if not self._db_ok:
            self._fallback_audit.append({"operation": operation, "target": target, "detail": detail, "logged_at": now})
            return
        self._conn.execute(
            "INSERT INTO audit (operation, target, detail, logged_at) VALUES (?, ?, ?, ?)",
            (operation, target, detail, now),
        )
        self._conn.commit()

    def forget_person(self, name: str, cascade_facts: bool = True) -> Dict:
        self._record("forget_person", name)
        removed_face = get_face_memory()._delete_person(name)
        removed_facts = get_long_term_memory()._delete_fact(name) if cascade_facts else 0
        return {"target": "person", "name": name, "face_entry_removed": removed_face, "facts_removed": removed_facts}

    def forget_place(self, name: str, cascade_facts: bool = False) -> Dict:
        self._record("forget_place", name)
        removed_place = get_place_memory()._delete_place(name)
        removed_facts = get_long_term_memory()._delete_fact(name) if cascade_facts else 0
        return {"target": "place", "name": name, "place_entry_removed": removed_place, "facts_removed": removed_facts}

    def forget_habit(self, action: str) -> Dict:
        self._record("forget_habit", action)
        removed = get_habit_memory()._delete_action(action)
        return {"target": "habit", "action": action, "occurrences_removed": removed}

    def forget_fact(self, subject: str, predicate: Optional[str] = None) -> Dict:
        self._record("forget_fact", subject, detail=predicate or "*")
        removed = get_long_term_memory()._delete_fact(subject, predicate)
        return {"target": "fact", "subject": subject, "predicate": predicate, "facts_removed": removed}

    def forget_session(self) -> Dict:
        """Clears short_term.py only - long_term/face/place/habit are
        untouched, since those were explicitly opted into persistence
        and a session ending is not itself a forget request for them."""
        self._record("forget_session", "short_term")
        get_short_term_memory().__init__()  # reset in-place, cheapest correct way to clear it
        return {"target": "session", "cleared": True}

    def forget_everything(self, confirm: bool = False) -> Dict:
        if not confirm:
            return {"error": "forget_everything requires confirm=True - refusing a silent full wipe"}
        self._record("forget_everything", "*", detail="full MEMORY/ wipe")
        for person in get_face_memory().known_people():
            get_face_memory()._delete_person(person["name"])
        for place in get_place_memory().known_places():
            get_place_memory()._delete_place(place["name"])
        for fact in get_long_term_memory().all_facts():
            get_long_term_memory()._delete_fact(fact["subject"], fact["predicate"])
        for habit in get_habit_memory().detected_habits(min_occurrences=1):
            get_habit_memory()._delete_action(habit["action"])
        get_short_term_memory().__init__()
        return {"target": "everything", "wiped": True}

    def audit_log(self, limit: int = 20) -> List[Dict]:
        if not self._db_ok:
            return self._fallback_audit[-limit:]
        cur = self._conn.cursor()
        cur.execute("SELECT operation, target, detail, logged_at FROM audit ORDER BY logged_at DESC LIMIT ?", (limit,))
        cols = ["operation", "target", "detail", "logged_at"]
        return [dict(zip(cols, row)) for row in cur.fetchall()]


_forgetter: Optional[Forget] = None


def get_forgetter() -> Forget:
    global _forgetter
    if _forgetter is None:
        _forgetter = Forget()
    return _forgetter
