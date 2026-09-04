"""
Authentication
==============
Local passphrase gate for sensitive operations - unlocking security/vault.py,
or (optionally) anything core/permissions.py already flags as
DESTRUCTIVE_TOOLS. This is single-user, local-machine auth (there's no
concept of multiple accounts) - the goal is "someone with a terminal open
to my machine can't dump saved credentials without the passphrase", not
multi-tenant access control.

Passphrase is never stored - only a PBKDF2-HMAC-SHA256 hash of it, salted
with security/encryption_keys.get_or_create_salt(). A short-lived session
token avoids re-prompting for every single tool call once unlocked.
"""

import hashlib
import hmac
import secrets
import sqlite3
import time
from pathlib import Path
from typing import Dict, Optional

from security.encryption_keys import get_or_create_salt

DB_PATH = Path(__file__).resolve().parents[1] / "storage" / "sqlite" / "auth.db"

PBKDF2_ITERATIONS = 200_000
DEFAULT_SESSION_TTL_SECONDS = 15 * 60  # re-auth every 15 minutes of inactivity


def _hash_passphrase(passphrase: str) -> str:
    salt = get_or_create_salt()
    digest = hashlib.pbkdf2_hmac("sha256", passphrase.encode("utf-8"), salt, PBKDF2_ITERATIONS)
    return digest.hex()


class AuthManager:
    """Set/verify a local passphrase and track a short-lived unlock session."""

    def __init__(self):
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
        self._conn.execute("""CREATE TABLE IF NOT EXISTS credentials (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                passphrase_hash TEXT NOT NULL,
                created_at REAL,
                updated_at REAL
            )""")
        self._conn.commit()
        self._session_token: Optional[str] = None
        self._session_expires_at: float = 0.0

    def is_configured(self) -> bool:
        """Whether a passphrase has been set yet."""
        cur = self._conn.cursor()
        cur.execute("SELECT 1 FROM credentials WHERE id = 1")
        return cur.fetchone() is not None

    def set_passphrase(self, passphrase: str) -> Dict:
        """Set (or change) the passphrase. Requires the caller to already
        be authenticated if one is already configured (checked by the caller,
        e.g. security/vault.py, via require_auth() before calling this)."""
        try:
            if not passphrase or len(passphrase) < 6:
                return {"error": "Passphrase must be at least 6 characters"}

            now = time.time()
            passphrase_hash = _hash_passphrase(passphrase)
            cur = self._conn.cursor()
            cur.execute(
                """INSERT INTO credentials (id, passphrase_hash, created_at, updated_at)
                   VALUES (1, ?, ?, ?)
                   ON CONFLICT(id) DO UPDATE SET passphrase_hash = excluded.passphrase_hash,
                                                  updated_at = excluded.updated_at""",
                (passphrase_hash, now, now),
            )
            self._conn.commit()
            return {"success": True}
        except Exception as e:
            return {"error": str(e)}

    def verify(self, passphrase: str, ttl_seconds: int = DEFAULT_SESSION_TTL_SECONDS) -> Dict:
        """Check the passphrase. On success, starts/refreshes an unlock
        session so is_authenticated() returns True for `ttl_seconds`."""
        try:
            cur = self._conn.cursor()
            cur.execute("SELECT passphrase_hash FROM credentials WHERE id = 1")
            row = cur.fetchone()
            if row is None:
                return {"error": "No passphrase has been set yet - call set_passphrase() first"}

            candidate_hash = _hash_passphrase(passphrase)
            if not hmac.compare_digest(candidate_hash, row[0]):
                return {"success": False, "error": "Incorrect passphrase"}

            self._session_token = secrets.token_hex(16)
            self._session_expires_at = time.time() + ttl_seconds
            return {"success": True, "session_token": self._session_token, "expires_in": ttl_seconds}
        except Exception as e:
            return {"error": str(e)}

    def is_authenticated(self) -> bool:
        """Whether there's a currently-valid unlock session."""
        return self._session_token is not None and time.time() < self._session_expires_at

    def require_auth(self) -> Dict:
        """Convenience gate for callers: returns {"success": True} if
        currently authenticated, else an error dict explaining why - so
        e.g. security/vault.py can do `if "error" in require_auth(): return ...`."""
        if not self.is_configured():
            return {"error": "No passphrase configured - call set_passphrase() first"}
        if not self.is_authenticated():
            return {"error": "Not authenticated - call verify() with the passphrase first"}
        return {"success": True}

    def lock(self) -> Dict:
        """End the current session immediately, without waiting for TTL expiry."""
        self._session_token = None
        self._session_expires_at = 0.0
        return {"success": True, "locked": True}


_manager: Optional[AuthManager] = None


def get_auth_manager() -> AuthManager:
    global _manager
    if _manager is None:
        _manager = AuthManager()
    return _manager
