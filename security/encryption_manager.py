"""
Encryption manager (Phase 26 - Security & Privacy)
=====================================================
Higher-level "what should be encrypted, and where" orchestration on top
of security/encryption.py's EncryptionManager (the actual Fernet
encrypt/decrypt primitive - this module never touches cryptography
directly, it delegates every byte of real crypto to that module, the
same way security/vault.py already does). Two things this adds that
encryption.py deliberately doesn't have:

  1. Structured-record helpers - encrypt_fields()/decrypt_fields() for
     "only some keys in this dict are sensitive" (a row, a config
     block), and classify_and_encrypt() for "figure out which keys are
     sensitive yourself" using a key-name heuristic plus
     security/data_anonymizer.py's PII scan on the values.

  2. A concrete integrated call site: memory/short_term/notes.py's
     quick-notes file (storage.plaintext-on-disk ultron_notes.txt) now
     runs every note through encrypt_note_if_sensitive() before writing
     and decrypt_note_line() on read - see the patch in notes.py. A
     note that mentions no PII/secrets is stored exactly as before
     (plaintext, human-readable in a text editor); a note containing an
     email/phone/card/API key is stored as an encrypted blob instead,
     transparently decrypted back on read_notes(). This was the one
     genuinely plaintext-on-disk surface in the existing codebase -
     everywhere else sensitive (vault, this) already goes through
     encryption.py one way or another.

Every encrypt/decrypt performed here is also logged to security/audit.py
(field names and counts only - never plaintext values), same as vault.py.
"""

from typing import Dict, List, Optional

from security.encryption import get_encryption_manager
from security.data_anonymizer import get_data_anonymizer
from core.logger import get_logger

logger = get_logger("ultron.security.encryption_manager")

# Key-name substrings (case-insensitive) treated as sensitive regardless
# of what data_anonymizer's content scan finds - a field literally named
# "password" should be encrypted even if its value doesn't look like any
# known PII pattern.
SENSITIVE_KEY_HINTS = ("password", "secret", "token", "api_key", "apikey", "credit_card", "ssn", "private_key")

# The note-encryption marker prefix - deliberately distinct from a
# Fernet token's own shape so a line can be recognized as
# "encrypted note" before attempting to decrypt it.
NOTE_MARKER = "[ENC]"


class RecordEncryptionManager:
    """encrypt_fields()/decrypt_fields()/classify_and_encrypt() for
    structured data, plus encrypt_note_if_sensitive()/decrypt_note_line()
    for the flat quick-notes file. Delegates all actual crypto to
    security.encryption.EncryptionManager."""

    def __init__(self):
        self._cipher = get_encryption_manager()
        self._anonymizer = get_data_anonymizer()

    # -- structured records ---------------------------------------------------
    def encrypt_fields(self, record: Dict, fields: List[str]) -> Dict:
        """Returns {"success", "record"} with the given `fields` replaced
        by their encrypted tokens in a copy of `record`, and an
        "_encrypted_fields" list added so decrypt_fields() knows what to
        reverse without being told again. Fields absent or None in
        `record` are skipped, not errored. Aborts (no partial encryption)
        if any present field fails to encrypt."""
        result = dict(record)
        encrypted_now: List[str] = []
        for field in fields:
            value = record.get(field)
            if value is None:
                continue
            outcome = self._cipher.encrypt(str(value))
            if "error" in outcome:
                self._audit().record("encryption_manager_encrypt_fields", {"field": field}, success=False)
                return {"error": f"Failed to encrypt field '{field}': {outcome['error']}"}
            result[field] = outcome["token"]
            encrypted_now.append(field)

        if encrypted_now:
            existing = set(result.get("_encrypted_fields", []))
            result["_encrypted_fields"] = sorted(existing | set(encrypted_now))
            self._audit().record("encryption_manager_encrypt_fields", {"fields": encrypted_now}, success=True)
        return {"success": True, "record": result}

    def decrypt_fields(self, record: Dict, fields: Optional[List[str]] = None) -> Dict:
        """Reverses encrypt_fields(). `fields` defaults to the record's own
        "_encrypted_fields" list, so a caller that just wants "give me
        this record back in the clear" doesn't need to remember which
        fields it encrypted."""
        target_fields = fields if fields is not None else record.get("_encrypted_fields", [])
        result = dict(record)
        decrypted_now: List[str] = []
        for field in target_fields:
            token = record.get(field)
            if token is None:
                continue
            outcome = self._cipher.decrypt(str(token))
            if "error" in outcome:
                self._audit().record("encryption_manager_decrypt_fields", {"field": field}, success=False)
                return {"error": f"Failed to decrypt field '{field}': {outcome['error']}"}
            result[field] = outcome["plaintext"]
            decrypted_now.append(field)

        remaining = set(result.get("_encrypted_fields", [])) - set(decrypted_now)
        if remaining:
            result["_encrypted_fields"] = sorted(remaining)
        else:
            result.pop("_encrypted_fields", None)
        if decrypted_now:
            self._audit().record("encryption_manager_decrypt_fields", {"fields": decrypted_now}, success=True)
        return {"success": True, "record": result}

    def classify_and_encrypt(self, record: Dict) -> Dict:
        """Auto-detects which top-level string fields look sensitive - by
        key name (SENSITIVE_KEY_HINTS) or by content (data_anonymizer
        flags a BLOCK-worthy category in the value) - and encrypts just
        those, via encrypt_fields(). Fields it doesn't flag are left
        exactly as-is, so this is safe to run over an arbitrary dict."""
        sensitive_fields = []
        for key, value in record.items():
            if key.startswith("_") or not isinstance(value, str):
                continue
            key_lower = key.lower()
            if any(hint in key_lower for hint in SENSITIVE_KEY_HINTS):
                sensitive_fields.append(key)
                continue
            found = self._anonymizer.scan(value)
            if any(category in found for category in ("credit_card", "api_key")):
                sensitive_fields.append(key)

        if not sensitive_fields:
            return {"success": True, "record": dict(record)}
        return self.encrypt_fields(record, sensitive_fields)

    # -- flat quick-notes file --------------------------------------------------
    def encrypt_note_if_sensitive(self, text: str) -> Dict:
        """Returns {"stored_text", "encrypted": bool} - `stored_text` is
        what memory/short_term/notes.py should actually write to disk:
        the original text unchanged if nothing sensitive was detected, or
        a NOTE_MARKER-prefixed encrypted token if it was."""
        if not text or not self._anonymizer.has_pii(text):
            return {"stored_text": text, "encrypted": False}

        outcome = self._cipher.encrypt(text)
        if "error" in outcome:
            # Fail open rather than lose the note entirely - matches the
            # rest of the codebase's "optional feature degrades, never
            # breaks the core action" philosophy. Logged either way.
            logger.warning(f"Note encryption failed, storing in the clear: {outcome['error']}")
            self._audit().record(
                "encryption_manager_note", {"encrypted": False, "error": outcome["error"]}, success=False
            )
            return {"stored_text": text, "encrypted": False}

        self._audit().record("encryption_manager_note", {"encrypted": True}, success=True)
        return {"stored_text": f"{NOTE_MARKER}{outcome['token']}", "encrypted": True}

    def decrypt_note_line(self, line: str) -> str:
        """Reverses encrypt_note_if_sensitive() for one already-timestamped
        line (`[2026-08-12 10:00] [ENC]<token>`). Lines without the marker
        pass through unchanged - old plaintext notes keep working exactly
        as before this phase."""
        marker_pos = line.find(NOTE_MARKER)
        if marker_pos == -1:
            return line
        prefix = line[:marker_pos]
        token = line[marker_pos + len(NOTE_MARKER) :]
        outcome = self._cipher.decrypt(token)
        if "error" in outcome:
            return f"{prefix}[unreadable encrypted note: {outcome['error']}]"
        return f"{prefix}{outcome['plaintext']}"

    def _audit(self):
        from security.audit import get_audit_log

        return get_audit_log()


_manager: Optional[RecordEncryptionManager] = None


def get_record_encryption_manager() -> RecordEncryptionManager:
    global _manager
    if _manager is None:
        _manager = RecordEncryptionManager()
    return _manager
