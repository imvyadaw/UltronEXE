"""
Encryption keys
===============
Generates and persists the Fernet key security/encryption.py uses for
symmetric encryption, and the salt security/authentication.py uses for
password hashing. Kept as its own module (rather than inline in
encryption.py) so both files - and anything else in security/ - share
exactly one key file instead of each rolling its own.

The key file lives outside of storage/backups|exports (those are meant
to be portable/shareable) at storage/secure/, and is created with
owner-only permissions where the OS supports it (POSIX chmod 600;
best-effort no-op on Windows, matching the rest of Ultron which already
treats Windows-only APIs as optional throughout windows/).
"""

import os
import secrets
import stat
from pathlib import Path
from typing import Dict

SECURE_DIR = Path(__file__).resolve().parents[1] / "storage" / "secure"
KEY_FILE = SECURE_DIR / "encryption.key"
SALT_FILE = SECURE_DIR / "auth.salt"


def _restrict_permissions(path: Path) -> None:
    """Best-effort owner-only file permissions. No-op on platforms
    (Windows) where chmod doesn't map to real ACL restriction - this is
    a hardening step, not the only line of defense."""
    try:
        os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)
    except (OSError, NotImplementedError):
        from core.error_trace import log_swallowed as _lsw

        _lsw("security.encryption_keys._restrict_permissions")


def _ensure_secure_dir() -> None:
    SECURE_DIR.mkdir(parents=True, exist_ok=True)
    _restrict_permissions(SECURE_DIR)


def get_or_create_encryption_key() -> bytes:
    """Return the persistent Fernet key, generating one on first use.
    Losing this file makes previously-encrypted data unrecoverable -
    back it up via storage/backups/ like any other sensitive file."""
    from cryptography.fernet import Fernet

    _ensure_secure_dir()
    if KEY_FILE.exists():
        return KEY_FILE.read_bytes()

    key = Fernet.generate_key()
    KEY_FILE.write_bytes(key)
    _restrict_permissions(KEY_FILE)
    return key


def get_or_create_salt() -> bytes:
    """Return the persistent salt used for password hashing. Separate
    from the encryption key: rotating one should never invalidate the other."""
    _ensure_secure_dir()
    if SALT_FILE.exists():
        return SALT_FILE.read_bytes()

    salt = secrets.token_bytes(16)
    SALT_FILE.write_bytes(salt)
    _restrict_permissions(SALT_FILE)
    return salt


def rotate_encryption_key() -> Dict:
    """Generate and save a brand-new encryption key, overwriting the old
    one. Anything encrypted under the old key becomes unreadable - only
    call this right after re-encrypting existing data (see
    security/encryption.py's rotate_key() workflow), not standalone."""
    try:
        from cryptography.fernet import Fernet

        _ensure_secure_dir()
        old_key = KEY_FILE.read_bytes() if KEY_FILE.exists() else None
        new_key = Fernet.generate_key()
        KEY_FILE.write_bytes(new_key)
        _restrict_permissions(KEY_FILE)
        return {"success": True, "rotated": True, "had_previous_key": old_key is not None}
    except Exception as e:
        return {"error": str(e)}
