"""
Contacts agent
==============
Local, offline contacts store - no Google/Outlook OAuth required, same
pattern as agents/calendar_agent.py (SQLite under storage/sqlite/).
Exists so voice/text commands can resolve a name to a number/email
instead of the user having to dictate a raw phone number - e.g.
call_phone (PHASE_18_7_AUTOMATION/ACTIONS/call_phone.py, wired in
core/executor.py) accepts a `name` and looks it up here when no
`number` is given directly.

Matching is deliberately simple (exact match first, then
case-insensitive substring) rather than fuzzy/phonetic - a wrong
number handed to call_phone is a real-world action with real-world
consequences, so an ambiguous or no match returns an explicit error
for the caller to resolve rather than guessing.
"""

import sqlite3
import time
from pathlib import Path
from typing import Dict, Optional

from agents.base_agent import BaseAgent

DB_PATH = Path(__file__).resolve().parent.parent / "storage" / "sqlite" / "contacts.db"


class ContactsAgent(BaseAgent):
    """Create, find, list, and remove local contacts."""

    capabilities = ["contacts", "phonebook", "address book"]

    def __init__(self):
        super().__init__("contacts", "Local offline contacts store (SQLite) - add/find/list/remove contacts")
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
        self._conn.execute("""CREATE TABLE IF NOT EXISTS contacts (
                name TEXT PRIMARY KEY,
                phone TEXT,
                email TEXT,
                notes TEXT,
                created_at REAL
            )""")
        self._conn.commit()

    def add_contact(self, name: str, phone: str = "", email: str = "", notes: str = "") -> Dict:
        """Add or overwrite a contact by name. At least one of
        phone/email should be given, but neither is enforced here -
        a contact with notes only is still valid."""
        if not name or not name.strip():
            return {"error": "name is required"}
        try:
            self._conn.execute(
                "INSERT INTO contacts (name, phone, email, notes, created_at) VALUES (?, ?, ?, ?, ?) "
                "ON CONFLICT(name) DO UPDATE SET phone=excluded.phone, email=excluded.email, notes=excluded.notes",
                (name.strip(), phone.strip(), email.strip(), notes, time.time()),
            )
            self._conn.commit()
            return {"success": True, "name": name.strip(), "phone": phone.strip(), "email": email.strip()}
        except Exception as e:
            return {"error": str(e)}

    def find_contact(self, name: str) -> Dict:
        """Look up a contact by name. Exact match (case-insensitive)
        first; if none, falls back to a substring match - but only if
        exactly one contact matches, since silently picking one of
        several similarly-named contacts for something like
        call_phone would be worse than asking the caller to
        disambiguate. Returns {"found": bool, "contact": {...} | None,
        "error": Optional[str]} - "error" is only set on an ambiguous
        multi-match, not on a clean zero-match."""
        if not name or not name.strip():
            return {"found": False, "contact": None, "error": "name is required"}
        query = name.strip()
        try:
            cur = self._conn.cursor()
            cur.execute(
                "SELECT name, phone, email, notes FROM contacts WHERE LOWER(name) = LOWER(?)",
                (query,),
            )
            row = cur.fetchone()
            if row:
                return {"found": True, "contact": self._row_to_dict(row), "error": None}

            cur.execute(
                "SELECT name, phone, email, notes FROM contacts WHERE LOWER(name) LIKE LOWER(?)",
                (f"%{query}%",),
            )
            rows = cur.fetchall()
            if len(rows) == 1:
                return {"found": True, "contact": self._row_to_dict(rows[0]), "error": None}
            if len(rows) > 1:
                names = [r[0] for r in rows]
                return {
                    "found": False,
                    "contact": None,
                    "error": f"Multiple contacts match '{query}': {', '.join(names)}. Be more specific.",
                }
            return {"found": False, "contact": None, "error": None}
        except Exception as e:
            return {"found": False, "contact": None, "error": str(e)}

    def list_contacts(self) -> Dict:
        """List every saved contact."""
        try:
            cur = self._conn.cursor()
            cur.execute("SELECT name, phone, email, notes FROM contacts ORDER BY name")
            rows = cur.fetchall()
            return {"count": len(rows), "contacts": [self._row_to_dict(r) for r in rows]}
        except Exception as e:
            return {"error": str(e)}

    def delete_contact(self, name: str) -> Dict:
        """Delete a contact by exact name."""
        if not name or not name.strip():
            return {"error": "name is required"}
        try:
            cur = self._conn.cursor()
            cur.execute("DELETE FROM contacts WHERE LOWER(name) = LOWER(?)", (name.strip(),))
            self._conn.commit()
            if cur.rowcount == 0:
                return {"error": f"No contact found named '{name}'"}
            return {"success": True, "deleted": name.strip()}
        except Exception as e:
            return {"error": str(e)}

    @staticmethod
    def _row_to_dict(row) -> Dict:
        return {"name": row[0], "phone": row[1], "email": row[2], "notes": row[3]}


_contacts_agent: Optional[ContactsAgent] = None


def get_contacts_agent() -> ContactsAgent:
    global _contacts_agent
    if _contacts_agent is None:
        _contacts_agent = ContactsAgent()
    return _contacts_agent
