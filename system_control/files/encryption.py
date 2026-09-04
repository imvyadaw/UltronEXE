"""File Encryption
==================
Encrypt/decrypt individual files on disk with Fernet (AES-128-CBC +
HMAC via the `cryptography` package) - the same symmetric-encryption
primitive and persistent key store security/encryption.py already uses
for vault entries, reused here via
security.encryption_keys.get_or_create_encryption_key() rather than
rolling a second key file. That module's own docstring says the point
of a shared key file is exactly this: "share exactly one key file
instead of each rolling its own."

Scope: arbitrary user files (documents, exports, backups) that the
user wants encrypted at rest - not the vault, not
memory/*.py's own field-level encryption, both of which already have
their own call sites in security/. This is the "encrypt this file for
me" surface.

Falls back to a clear "not installed" error rather than crashing at
import time if `cryptography` isn't installed, same as
security/encryption.py.

encrypt_file/decrypt_file are confirm-gated like every other file-
mutating tool in this codebase, since both can overwrite an existing
file at the destination path.
"""

from pathlib import Path
from typing import Dict, Optional

try:
    from cryptography.fernet import Fernet, InvalidToken

    HAS_CRYPTOGRAPHY = True
except ImportError:
    HAS_CRYPTOGRAPHY = False

# Written as a prefix on every file this module encrypts, so
# is_file_encrypted() can tell "encrypted by us" apart from "any other
# binary file" without needing to attempt a real decrypt.
_MAGIC = b"ULTRONFENC1\n"


class FileEncryption:
    """Encrypt/decrypt individual files at rest using the shared Fernet key."""

    def _get_fernet(self):
        if not HAS_CRYPTOGRAPHY:
            return None
        from security.encryption_keys import get_or_create_encryption_key

        return Fernet(get_or_create_encryption_key())

    def is_file_encrypted(self, path: str) -> Dict:
        """Check whether a file was encrypted by this module (magic-prefix check, not a full decrypt)."""
        p = Path(path)
        if not p.exists() or not p.is_file():
            return {"error": f"File not found: {path}"}
        try:
            with p.open("rb") as f:
                head = f.read(len(_MAGIC))
            return {"success": True, "path": str(p), "encrypted": head == _MAGIC}
        except Exception as e:
            return {"error": str(e)}

    def encrypt_file(self, path: str, output_path: Optional[str] = None, confirm: bool = False) -> Dict:
        """Encrypt a file in place (or to output_path if given) using the
        shared Fernet key. Confirm-gated - overwrites the destination if
        it already exists."""
        if not HAS_CRYPTOGRAPHY:
            return {"error": "cryptography package is not installed - run: pip install cryptography"}
        src = Path(path)
        if not src.exists() or not src.is_file():
            return {"error": f"File not found: {path}"}
        dest = Path(output_path) if output_path else src
        if not confirm:
            return {
                "success": False,
                "needs_confirmation": True,
                "preview": f"Would encrypt {src} -> {dest} (overwrites destination if it exists)",
                "message": "Call again with confirm=true to apply.",
            }
        try:
            fernet = self._get_fernet()
            data = src.read_bytes()
            token = fernet.encrypt(data)
            dest.write_bytes(_MAGIC + token)
            return {
                "success": True,
                "path": str(src),
                "output_path": str(dest),
                "original_size": len(data),
                "encrypted_size": dest.stat().st_size,
            }
        except Exception as e:
            return {"error": str(e)}

    def decrypt_file(self, path: str, output_path: Optional[str] = None, confirm: bool = False) -> Dict:
        """Decrypt a file previously encrypted by encrypt_file(), in place
        (or to output_path if given). Confirm-gated - overwrites the
        destination if it already exists."""
        if not HAS_CRYPTOGRAPHY:
            return {"error": "cryptography package is not installed - run: pip install cryptography"}
        src = Path(path)
        if not src.exists() or not src.is_file():
            return {"error": f"File not found: {path}"}
        dest = Path(output_path) if output_path else src
        if not confirm:
            return {
                "success": False,
                "needs_confirmation": True,
                "preview": f"Would decrypt {src} -> {dest} (overwrites destination if it exists)",
                "message": "Call again with confirm=true to apply.",
            }
        try:
            raw = src.read_bytes()
            if not raw.startswith(_MAGIC):
                return {"error": f"{path} does not look like a file encrypted by this module " "(missing magic header)"}
            fernet = self._get_fernet()
            plaintext = fernet.decrypt(raw[len(_MAGIC) :])
            dest.write_bytes(plaintext)
            return {"success": True, "path": str(src), "output_path": str(dest), "size": len(plaintext)}
        except InvalidToken:
            return {"error": "Decryption failed - wrong key or corrupted file."}
        except Exception as e:
            return {"error": str(e)}
