"""
Data Vault (SECURITY)
========================
Encrypted-at-rest key/value store for whatever shouldn't sit in a
plaintext `.env` or config file long-term - a saved card number, a
personal note, a secondary API key. Built on `cryptography`'s Fernet
(AES-128-CBC + HMAC, authenticated), with the encryption key derived
from a master password via PBKDF2-HMAC-SHA256, never stored itself.

Deliberately NOT where this project's own operating credentials live
- WHATSAPP_ACCESS_TOKEN, GROQ_API_KEY and friends stay in `.env` and
os.environ, read directly by each CONNECT/*.py module, exactly as
today. This module is for user data the vault owner asks Ultron to
remember, gated behind face_lock/voice_lock rather than an
always-loaded environment variable.

unlock() must be called with the correct master password before any
store()/retrieve(); the derived key lives only in memory for that
VaultLock instance and is dropped on lock(). Wrong password, no
`cryptography`, or a corrupted vault file all collapse to
{"success": False, ...} rather than an exception.
"""

import base64
import json
import os
from typing import Dict, List, Optional

try:
    from cryptography.fernet import Fernet, InvalidToken
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

    _CRYPTOGRAPHY_AVAILABLE = True
except Exception:
    _CRYPTOGRAPHY_AVAILABLE = False

VAULT_FILE_ENV = "SECURITY_VAULT_FILE"
DEFAULT_VAULT_FILE = "data/security/vault.json"
PBKDF2_ITERATIONS = 390_000


def _derive_key(password: str, salt: bytes) -> bytes:
    kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=PBKDF2_ITERATIONS)
    return base64.urlsafe_b64encode(kdf.derive(password.encode("utf-8")))


class DataVault:
    """Password-gated encrypted key/value store. Use get_data_vault()."""

    def __init__(self):
        self._fernet = None  # only set while unlocked

    def is_available(self) -> bool:
        return _CRYPTOGRAPHY_AVAILABLE

    def _vault_path(self) -> str:
        path = os.environ.get(VAULT_FILE_ENV, DEFAULT_VAULT_FILE)
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        return path

    def _read_file(self) -> Dict:
        path = self._vault_path()
        if not os.path.exists(path):
            return {"salt": None, "entries": {}}
        with open(path) as fh:
            return json.load(fh)

    def _write_file(self, data: Dict) -> None:
        with open(self._vault_path(), "w") as fh:
            json.dump(data, fh)

    def exists(self) -> bool:
        """Whether a vault has ever been initialized (i.e. has a
        master password set), regardless of lock state."""
        return os.path.exists(self._vault_path())

    def is_unlocked(self) -> bool:
        return self._fernet is not None

    def unlock(self, password: str) -> Dict:
        """Derives the vault key from `password` and, if this is the
        first unlock ever, initializes an empty vault with a fresh
        salt. Wrong password on an existing vault is detected lazily,
        the first time retrieve() fails to decrypt - Fernet gives no
        way to check a key without a ciphertext to test it against.
        Returns {"success": bool, "error": Optional[str]}."""
        if not self.is_available():
            return {"success": False, "error": "cryptography not available"}
        if not password:
            return {"success": False, "error": "password required"}
        data = self._read_file()
        if data["salt"] is None:
            salt = os.urandom(16)
            data["salt"] = base64.b64encode(salt).decode("ascii")
            self._write_file(data)
        else:
            salt = base64.b64decode(data["salt"])
        key = _derive_key(password, salt)
        self._fernet = Fernet(key)
        return {"success": True, "error": None}

    def lock(self) -> None:
        """Drops the in-memory key. Stored entries are unaffected."""
        self._fernet = None

    def store(self, key: str, value: str) -> Dict:
        """Encrypts `value` and saves it under `key`, overwriting any
        existing entry. Returns {"success": bool, "error": Optional[str]}."""
        if not self.is_unlocked():
            return {"success": False, "error": "vault is locked"}
        if not key:
            return {"success": False, "error": "key required"}
        try:
            data = self._read_file()
            token = self._fernet.encrypt(value.encode("utf-8")).decode("ascii")
            data["entries"][key] = token
            self._write_file(data)
            return {"success": True, "error": None}
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    def retrieve(self, key: str) -> Dict:
        """Decrypts and returns the entry at `key`. Returns
        {"success": bool, "value": Optional[str], "error": Optional[str]}.
        An InvalidToken here (wrong password OR tampered file) is
        reported as "wrong password or corrupted vault" since Fernet
        can't tell the two apart."""
        if not self.is_unlocked():
            return {"success": False, "value": None, "error": "vault is locked"}
        data = self._read_file()
        if key not in data["entries"]:
            return {"success": False, "value": None, "error": f"'{key}' not found"}
        try:
            value = self._fernet.decrypt(data["entries"][key].encode("ascii")).decode("utf-8")
            return {"success": True, "value": value, "error": None}
        except InvalidToken:
            return {"success": False, "value": None, "error": "wrong password or corrupted vault"}
        except Exception as exc:
            return {"success": False, "value": None, "error": str(exc)}

    def delete(self, key: str) -> Dict:
        """Removes the entry at `key`. Works even while locked, since
        it doesn't need to decrypt anything. Returns
        {"success": bool, "error": Optional[str]}."""
        data = self._read_file()
        if key not in data["entries"]:
            return {"success": False, "error": f"'{key}' not found"}
        del data["entries"][key]
        self._write_file(data)
        return {"success": True, "error": None}

    def list_keys(self) -> List[str]:
        """Returns entry names (not values - no decryption needed or
        performed) even while locked."""
        return list(self._read_file()["entries"].keys())

    def change_password(self, old_password: str, new_password: str) -> Dict:
        """Re-encrypts every entry under a new master password.
        Returns {"success": bool, "error": Optional[str]}."""
        if not self.is_available():
            return {"success": False, "error": "cryptography not available"}
        unlock_result = self.unlock(old_password)
        if not unlock_result["success"]:
            return unlock_result
        try:
            data = self._read_file()
            decrypted = {}
            for key, token in data["entries"].items():
                decrypted[key] = self._fernet.decrypt(token.encode("ascii")).decode("utf-8")
        except InvalidToken:
            self.lock()
            return {"success": False, "error": "old_password is incorrect"}

        new_salt = os.urandom(16)
        new_key = _derive_key(new_password, new_salt)
        new_fernet = Fernet(new_key)
        data["salt"] = base64.b64encode(new_salt).decode("ascii")
        data["entries"] = {k: new_fernet.encrypt(v.encode("utf-8")).decode("ascii") for k, v in decrypted.items()}
        self._write_file(data)
        self._fernet = new_fernet
        return {"success": True, "error": None}


_data_vault: Optional[DataVault] = None


def get_data_vault() -> DataVault:
    global _data_vault
    if _data_vault is None:
        _data_vault = DataVault()
    return _data_vault
