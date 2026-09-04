"""
secure_enclave.py
====================
Encrypted-at-rest storage for the handful of genuinely sensitive
things ULTRON needs to hold onto: API keys, device pairing tokens,
anything skill_creator-generated skills read from an env var. Not a
literal hardware enclave (no TPM/SGX integration) - the name is
aspirational for "the one place secrets live encrypted, distinct from
every other plain-JSON store the rest of ULTRON uses."

Uses Fernet (AES-128-CBC + HMAC, from the `cryptography` package) with
a key you supply or that gets generated once and written to a
key file with owner-only permissions. Losing that key file means
losing everything encrypted with it - there is no recovery backdoor,
intentionally.

Dependencies: pip install cryptography
"""

from __future__ import annotations

import json
import logging
import os
import stat
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional

from cryptography.fernet import Fernet, InvalidToken

logger = logging.getLogger("ultron.secure_enclave")

DEFAULT_KEY_PATH = "ultron_data/shield/enclave.key"
DEFAULT_STORE_PATH = "ultron_data/shield/enclave.enc"


@dataclass
class SecretMetadata:
    name: str
    created_at: str
    updated_at: str


class SecureEnclave:
    """Encrypted key/value store for secrets. Values are opaque strings
    (encode/serialize anything more complex yourself before storing)."""

    def __init__(self, key_path: str = DEFAULT_KEY_PATH, store_path: str = DEFAULT_STORE_PATH):
        self.key_path = key_path
        self.store_path = store_path
        self._fernet = Fernet(self._load_or_create_key())
        self._secrets: Dict[str, str] = {}
        self._metadata: Dict[str, SecretMetadata] = {}
        self._load()

    def put(self, name: str, value: str) -> None:
        now = datetime.now().isoformat()
        created = self._metadata[name].created_at if name in self._metadata else now
        self._secrets[name] = value
        self._metadata[name] = SecretMetadata(name=name, created_at=created, updated_at=now)
        self._save()
        logger.info("Stored secret '%s'", name)  # never log the value itself

    def get(self, name: str) -> Optional[str]:
        return self._secrets.get(name)

    def delete(self, name: str) -> bool:
        existed = name in self._secrets
        self._secrets.pop(name, None)
        self._metadata.pop(name, None)
        if existed:
            self._save()
            logger.info("Deleted secret '%s'", name)
        return existed

    def list_names(self) -> List[str]:
        """Names only - never returns values in bulk."""
        return sorted(self._secrets.keys())

    def metadata(self, name: str) -> Optional[SecretMetadata]:
        return self._metadata.get(name)

    def rotate_key(self) -> None:
        """Re-encrypt everything under a freshly generated key. Do this
        periodically, or immediately if you suspect the key file was exposed."""
        new_key = Fernet.generate_key()
        new_fernet = Fernet(new_key)
        self._fernet = new_fernet
        self._write_key(new_key)
        self._save()
        logger.info("Enclave key rotated; all secrets re-encrypted")

    # ------------------------------------------------------------------ internal
    def _load_or_create_key(self) -> bytes:
        if os.path.exists(self.key_path):
            with open(self.key_path, "rb") as f:
                return f.read()
        key = Fernet.generate_key()
        self._write_key(key)
        return key

    def _write_key(self, key: bytes) -> None:
        os.makedirs(os.path.dirname(self.key_path), exist_ok=True)
        with open(self.key_path, "wb") as f:
            f.write(key)
        try:
            os.chmod(self.key_path, stat.S_IRUSR | stat.S_IWUSR)  # owner read/write only
        except OSError:
            from core.error_trace import log_swallowed as _lsw

            _lsw("ultron_shield.secure_enclave._write_key")

    def _load(self) -> None:
        if not os.path.exists(self.store_path):
            return
        try:
            with open(self.store_path, "rb") as f:
                blob = f.read()
            if not blob:
                return
            plaintext = self._fernet.decrypt(blob)
            raw = json.loads(plaintext)
            self._secrets = raw.get("secrets", {})
            self._metadata = {k: SecretMetadata(**v) for k, v in raw.get("metadata", {}).items()}
        except InvalidToken:
            logger.error(
                "Enclave store could not be decrypted with the current key - "
                "wrong key file, or the store is corrupted"
            )
        except (json.JSONDecodeError, OSError, TypeError) as exc:
            logger.error("Failed to load enclave store: %s", exc)

    def _save(self) -> None:
        raw = {
            "secrets": self._secrets,
            "metadata": {k: vars(v) for k, v in self._metadata.items()},
        }
        plaintext = json.dumps(raw).encode()
        ciphertext = self._fernet.encrypt(plaintext)
        os.makedirs(os.path.dirname(self.store_path), exist_ok=True)
        with open(self.store_path, "wb") as f:
            f.write(ciphertext)
        try:
            os.chmod(self.store_path, stat.S_IRUSR | stat.S_IWUSR)
        except OSError:
            from core.error_trace import log_swallowed as _lsw

            _lsw("ultron_shield.secure_enclave._save")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    enclave = SecureEnclave(
        key_path="ultron_data/shield/_demo_enclave.key", store_path="ultron_data/shield/_demo_enclave.enc"
    )
    enclave.put("WIDGETCO_API_KEY", "sk-demo-not-a-real-key")
    print("Names:", enclave.list_names())
    print("Get back:", enclave.get("WIDGETCO_API_KEY"))
    print("Metadata:", enclave.metadata("WIDGETCO_API_KEY"))

    # Confirm what's actually on disk is not plaintext.
    with open("ultron_data/shield/_demo_enclave.enc", "rb") as f:
        on_disk = f.read()
    assert b"sk-demo" not in on_disk
    print("Confirmed: ciphertext on disk does not contain the plaintext secret.")
