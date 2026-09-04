"""
Vault
=====
Encrypted secret store - API keys, passwords, tokens the user asks
Ultron to remember - built on top of the other three security/ modules:
- security/authentication.py gates every read/write behind the unlock session
- security/encryption.py encrypts values before they touch disk
- security/audit.py logs every access attempt (including failed/locked ones)

This is the module other parts of Ultron (e.g. a future skills/ tool like
"save my Wi-Fi password") should actually call, rather than using
encryption.py or authentication.py directly - it's the one place that
enforces all three together.
"""

import sqlite3
import time
from pathlib import Path
from typing import Dict, Optional

from security.authentication import get_auth_manager
from security.encryption import get_encryption_manager
from security.audit import get_audit_log

DB_PATH = Path(__file__).resolve().parents[1] / "storage" / "sqlite" / "vault.db"


class Vault:
    """Store/retrieve encrypted secrets, gated by an unlocked auth session."""

    def __init__(self):
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
        self._conn.execute("""CREATE TABLE IF NOT EXISTS secrets (
                name TEXT PRIMARY KEY,
                token TEXT NOT NULL,
                updated_at REAL
            )""")
        self._conn.commit()
        self._auth = get_auth_manager()
        self._encryption = get_encryption_manager()
        self._audit = get_audit_log()

    def _check_auth(self, action: str) -> Optional[Dict]:
        """Returns an error dict (and logs the denial) if not authenticated,
        else None - callers do `denial = self._check_auth(...); if denial: return denial`."""
        auth_result = self._auth.require_auth()
        if "error" in auth_result:
            self._audit.record(f"vault_{action}", {"reason": auth_result["error"]}, success=False)
            return auth_result
        return None

    def store(self, name: str, value: str) -> Dict:
        """Encrypt and save a secret under `name` (e.g. 'home_wifi_password')."""
        denial = self._check_auth("store")
        if denial:
            return denial
        try:
            encrypted = self._encryption.encrypt(value)
            if "error" in encrypted:
                self._audit.record("vault_store", {"name": name}, success=False)
                return encrypted

            cur = self._conn.cursor()
            cur.execute(
                "INSERT INTO secrets (name, token, updated_at) VALUES (?, ?, ?) "
                "ON CONFLICT(name) DO UPDATE SET token = excluded.token, updated_at = excluded.updated_at",
                (name, encrypted["token"], time.time()),
            )
            self._conn.commit()
            self._audit.record("vault_store", {"name": name}, success=True)
            return {"success": True, "name": name}
        except Exception as e:
            self._audit.record("vault_store", {"name": name}, success=False)
            return {"error": str(e)}

    def retrieve(self, name: str) -> Dict:
        """Decrypt and return the secret stored under `name`."""
        denial = self._check_auth("retrieve")
        if denial:
            return denial
        try:
            cur = self._conn.cursor()
            cur.execute("SELECT token FROM secrets WHERE name = ?", (name,))
            row = cur.fetchone()
            if row is None:
                self._audit.record("vault_retrieve", {"name": name}, success=False)
                return {"error": f"No secret stored under '{name}'"}

            decrypted = self._encryption.decrypt(row[0])
            if "error" in decrypted:
                self._audit.record("vault_retrieve", {"name": name}, success=False)
                return decrypted

            self._audit.record("vault_retrieve", {"name": name}, success=True)
            return {"success": True, "name": name, "value": decrypted["plaintext"]}
        except Exception as e:
            self._audit.record("vault_retrieve", {"name": name}, success=False)
            return {"error": str(e)}

    def delete(self, name: str) -> Dict:
        denial = self._check_auth("delete")
        if denial:
            return denial
        try:
            cur = self._conn.cursor()
            cur.execute("DELETE FROM secrets WHERE name = ?", (name,))
            self._conn.commit()
            self._audit.record("vault_delete", {"name": name}, success=cur.rowcount > 0)
            return {"success": True, "deleted": cur.rowcount > 0}
        except Exception as e:
            return {"error": str(e)}

    def list_names(self) -> Dict:
        """List stored secret NAMES only - never decrypts values just to list them."""
        denial = self._check_auth("list")
        if denial:
            return denial
        try:
            cur = self._conn.cursor()
            cur.execute("SELECT name, updated_at FROM secrets ORDER BY name")
            rows = cur.fetchall()
            self._audit.record("vault_list", {"count": len(rows)}, success=True)
            return {"secrets": [{"name": r[0], "updated_at": r[1]} for r in rows]}
        except Exception as e:
            return {"error": str(e)}

    def rotate_encryption(self) -> Dict:
        """Re-encrypt every stored secret under a freshly rotated key -
        the only safe way to rotate once secrets already exist."""
        denial = self._check_auth("rotate")
        if denial:
            return denial
        try:
            cur = self._conn.cursor()
            cur.execute("SELECT name, token FROM secrets")
            rows = cur.fetchall()

            tokens = [t for _, t in rows]
            rotate_result = self._encryption.rotate_key(re_encrypt=tokens)
            if "error" in rotate_result:
                self._audit.record("vault_rotate_key", {}, success=False)
                return rotate_result

            new_tokens = rotate_result["re_encrypted"]
            for (name, _), new_token in zip(rows, new_tokens):
                cur.execute(
                    "UPDATE secrets SET token = ?, updated_at = ? WHERE name = ?",
                    (new_token, time.time(), name),
                )
            self._conn.commit()
            self._audit.record("vault_rotate_key", {"secret_count": len(rows)}, success=True)
            return {"success": True, "re_encrypted_count": len(rows)}
        except Exception as e:
            self._audit.record("vault_rotate_key", {}, success=False)
            return {"error": str(e)}


_vault: Optional[Vault] = None


def get_vault() -> Vault:
    global _vault
    if _vault is None:
        _vault = Vault()
    return _vault
