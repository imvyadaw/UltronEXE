"""Quick notes
============
Save/read timestamped quick notes (ultron_notes.txt in the home folder). A lightweight stand-in until long_term/vector_db memory lands.

Phase 26 (Security & Privacy): this was the one place in the codebase
still writing potentially-sensitive user text to disk in the clear. Every
note now passes through security/encryption_manager.py's
encrypt_note_if_sensitive() before being written - a note with no
detected PII/secret is stored exactly as before (plaintext, still
readable by opening the .txt file), a note that does mention one (an
email, a card number, an API key) is stored as an encrypted blob instead
and transparently decrypted back by read_notes(). Old plaintext notes
from before this phase keep reading back fine either way.
"""

from pathlib import Path
from typing import Dict
from datetime import datetime

from security.encryption_manager import get_record_encryption_manager


class NotesStore:
    """Timestamped scratch notes - simplest form of 'memory' Ultron currently has."""

    def __init__(self):
        self.home_dir = Path.home()

    def save_note(self, text: str) -> Dict:
        """Save a quick timestamped note to ultron_notes.txt in the home
        folder - encrypted first if it looks sensitive (see module docstring)."""
        try:
            notes_path = self.home_dir / "ultron_notes.txt"
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
            outcome = get_record_encryption_manager().encrypt_note_if_sensitive(text)
            with open(notes_path, "a", encoding="utf-8") as f:
                f.write(f"[{timestamp}] {outcome['stored_text']}\n")
            return {"success": True, "saved": text, "file": str(notes_path), "encrypted": outcome["encrypted"]}
        except Exception as e:
            return {"error": str(e)}

    def read_notes(self) -> Dict:
        """Read back all saved notes, decrypting any that were stored encrypted."""
        try:
            notes_path = self.home_dir / "ultron_notes.txt"
            if not notes_path.exists():
                return {"notes": [], "count": 0}
            raw_lines = [l for l in notes_path.read_text(encoding="utf-8").strip().split("\n") if l]
            manager = get_record_encryption_manager()
            lines = [manager.decrypt_note_line(l) for l in raw_lines]
            return {"notes": lines, "count": len(lines)}
        except Exception as e:
            return {"error": str(e)}
