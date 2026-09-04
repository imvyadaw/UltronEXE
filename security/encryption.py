"""
Encryption
==========
Symmetric encryption (Fernet - AES-128-CBC + HMAC, via the `cryptography`
package) for sensitive values before they hit disk: vault entries
(security/vault.py), and optionally fields in memory/*.py that shouldn't
sit in plaintext SQLite (e.g. a saved API key mentioned mid-conversation).

Not for network transport security (networking/http_client.py already
gets that for free from HTTPS) - this is purely at-rest encryption for
local files.

Falls back to a clear "not installed" error rather than crashing at
import time if the `cryptography` package isn't installed, matching how
ai/embeddings.py treats sentence-transformers as optional.
"""

import base64
from typing import Dict, Optional

from security.encryption_keys import get_or_create_encryption_key

try:
    from cryptography.fernet import Fernet, InvalidToken

    HAS_CRYPTOGRAPHY = True
except ImportError:
    HAS_CRYPTOGRAPHY = False


class EncryptionManager:
    """Encrypt/decrypt strings using the shared persistent Fernet key."""

    def __init__(self):
        self._fernet: Optional["Fernet"] = None

    def _get_fernet(self):
        if not HAS_CRYPTOGRAPHY:
            raise RuntimeError(
                "The 'cryptography' package is required for encryption. " "Install it with: pip install cryptography"
            )
        if self._fernet is None:
            self._fernet = Fernet(get_or_create_encryption_key())
        return self._fernet

    def encrypt(self, plaintext: str) -> Dict:
        """Encrypt a string, returning a base64 token safe to store in SQLite/JSON."""
        try:
            token = self._get_fernet().encrypt(plaintext.encode("utf-8"))
            return {"success": True, "token": token.decode("utf-8")}
        except Exception as e:
            return {"error": str(e)}

    def decrypt(self, token: str) -> Dict:
        """Decrypt a token produced by encrypt(). Fails clearly (not
        silently) if the token was tampered with or the key has rotated."""
        try:
            plaintext = self._get_fernet().decrypt(token.encode("utf-8"))
            return {"success": True, "plaintext": plaintext.decode("utf-8")}
        except InvalidToken:
            return {"error": "Invalid or tampered token, or the encryption key has changed"}
        except Exception as e:
            return {"error": str(e)}

    def encrypt_bytes(self, data: bytes) -> Dict:
        try:
            token = self._get_fernet().encrypt(data)
            return {"success": True, "token": base64.urlsafe_b64encode(token).decode("ascii")}
        except Exception as e:
            return {"error": str(e)}

    def decrypt_bytes(self, token_b64: str) -> Dict:
        try:
            token = base64.urlsafe_b64decode(token_b64.encode("ascii"))
            data = self._get_fernet().decrypt(token)
            return {"success": True, "data": data}
        except InvalidToken:
            return {"error": "Invalid or tampered token, or the encryption key has changed"}
        except Exception as e:
            return {"error": str(e)}

    def rotate_key(self, re_encrypt: Optional[list] = None) -> Dict:
        """Rotate the encryption key. If `re_encrypt` (a list of plaintext
        strings previously protected under the old key) is given, decrypts
        them under the old key first, then re-encrypts everything under
        the new one - call this instead of encryption_keys.rotate_encryption_key()
        directly whenever there's existing encrypted data to preserve."""
        from security.encryption_keys import rotate_encryption_key

        try:
            decrypted_plain = []
            if re_encrypt:
                for token in re_encrypt:
                    result = self.decrypt(token)
                    if "error" in result:
                        return {"error": f"Could not decrypt existing data before rotation: {result['error']}"}
                    decrypted_plain.append(result["plaintext"])

            rotate_result = rotate_encryption_key()
            if "error" in rotate_result:
                return rotate_result

            self._fernet = None  # force reload of the new key on next use

            re_encrypted = [self.encrypt(p)["token"] for p in decrypted_plain] if decrypted_plain else []
            return {"success": True, "re_encrypted": re_encrypted}
        except Exception as e:
            return {"error": str(e)}


_manager: Optional[EncryptionManager] = None


def get_encryption_manager() -> EncryptionManager:
    global _manager
    if _manager is None:
        _manager = EncryptionManager()
    return _manager
