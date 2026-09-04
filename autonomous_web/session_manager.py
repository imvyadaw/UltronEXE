"""
session_manager.py
===================
Saves and restores browser session state (cookies + local storage) so
ULTRON doesn't need to log in again on every run - the same thing
Playwright's own `storage_state` feature is for.

Security note: this file is your login session in plain form - anyone
who gets a copy of it can potentially act as you on that site. It's
stored under a local, per-site file rather than one shared blob, and
`encrypt=True` (default) wraps it with a key derived from a passphrase
you provide, using the `cryptography` package. If you skip the
passphrase, it falls back to a clear warning and plain-text storage -
that's opt-out, not opt-in, on purpose.

Dependencies: pip install playwright cryptography
"""

from __future__ import annotations

import base64
import json
import logging
from pathlib import Path
from typing import Optional

from playwright.sync_api import BrowserContext

logger = logging.getLogger("ultron.session_manager")

try:
    from cryptography.fernet import Fernet
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

    _CRYPTO_AVAILABLE = True
except ImportError:  # pragma: no cover
    _CRYPTO_AVAILABLE = False


def _derive_key(passphrase: str, salt: bytes) -> bytes:
    kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=390_000)
    return base64.urlsafe_b64encode(kdf.derive(passphrase.encode("utf-8")))


class SessionManager:
    def __init__(self, storage_dir: str = "./ultron_sessions"):
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)

    def _path_for(self, site_key: str) -> Path:
        safe = "".join(c if c.isalnum() else "_" for c in site_key)
        return self.storage_dir / f"{safe}.session"

    def save(self, context: BrowserContext, site_key: str, passphrase: Optional[str] = None) -> str:
        state = context.storage_state()
        raw = json.dumps(state).encode("utf-8")
        path = self._path_for(site_key)

        if passphrase and _CRYPTO_AVAILABLE:
            salt = Path(str(path) + ".salt")
            salt_bytes = salt.read_bytes() if salt.exists() else __import__("os").urandom(16)
            salt.write_bytes(salt_bytes)
            key = _derive_key(passphrase, salt_bytes)
            raw = Fernet(key).encrypt(raw)
            logger.info("Saved encrypted session for '%s' -> %s", site_key, path)
        else:
            if passphrase and not _CRYPTO_AVAILABLE:
                logger.warning("cryptography package not installed - saving session UNENCRYPTED")
            else:
                logger.warning("No passphrase given - saving session UNENCRYPTED at %s", path)

        path.write_bytes(raw)
        return str(path)

    def load(self, site_key: str, passphrase: Optional[str] = None) -> Optional[dict]:
        path = self._path_for(site_key)
        if not path.exists():
            return None
        raw = path.read_bytes()

        salt_path = Path(str(path) + ".salt")
        if passphrase and salt_path.exists() and _CRYPTO_AVAILABLE:
            key = _derive_key(passphrase, salt_path.read_bytes())
            try:
                raw = Fernet(key).decrypt(raw)
            except Exception:
                logger.error("Failed to decrypt session for '%s' - wrong passphrase?", site_key)
                return None

        try:
            return json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError:
            logger.error("Session file for '%s' is not valid JSON (encrypted but no passphrase given?)", site_key)
            return None

    def has_session(self, site_key: str) -> bool:
        return self._path_for(site_key).exists()

    def delete(self, site_key: str):
        path = self._path_for(site_key)
        salt_path = Path(str(path) + ".salt")
        for p in (path, salt_path):
            if p.exists():
                p.unlink()
        logger.info("Deleted session for '%s'", site_key)
