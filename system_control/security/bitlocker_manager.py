"""BitLocker Manager
=====================
Windows BitLocker drive-encryption control via the `manage-bde` CLI
and `BitLocker` PowerShell module - status per volume, enabling/
disabling encryption, lock/unlock, and recovery-key retrieval.
Distinct from the top-level security/encryption_manager.py (Ultron's
own file/data encryption for its own memory/config, not disk-level),
and from system_control/files (file permissions/sharing, not
volume-level encryption) - this is whole-volume disk encryption.

Status reads (get_status, list_volumes) need no admin. Enabling
encryption, disabling it, and locking/unlocking a volume are
confirm-gated and need admin - enabling can take significant time
and disabling removes real protection against offline data access.
get_recovery_key is confirm-gated on its own since it reveals a
secret that can decrypt the whole drive.
"""

import subprocess
import re
from typing import Dict, Optional


class BitLockerManager:
    """Inspect and control BitLocker volume encryption via manage-bde."""

    def _run(self, cmd: list, timeout: float = 30.0) -> Dict:
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
            return {
                "success": result.returncode == 0,
                "stdout": result.stdout.strip(),
                "stderr": result.stderr.strip(),
            }
        except FileNotFoundError:
            return {"error": f"{cmd[0]} not found - manage-bde is only available on Windows Pro/Enterprise/Education"}
        except subprocess.TimeoutExpired:
            return {"error": "Command timed out"}
        except Exception as e:
            return {"error": str(e)}

    def _admin_hint(self, err: str) -> str:
        if err and ("denied" in err.lower() or "not authorized" in err.lower() or "elevat" in err.lower()):
            return err + " - this needs ULTRON running as Administrator."
        return err

    def list_volumes(self) -> Dict:
        """List all volumes and their BitLocker protection status."""
        result = self._run(["manage-bde", "-status"])
        if "error" in result:
            return result
        if not result["success"]:
            return {"error": self._admin_hint(result["stderr"] or "manage-bde -status failed")}
        volumes = []
        blocks = re.split(r"\n(?=Volume )", result["stdout"])
        for block in blocks:
            m_letter = re.search(r"Volume (\S+)", block)
            m_pct = re.search(r"Percentage Encrypted:\s*([\d.]+)%", block)
            m_status = re.search(r"Conversion Status:\s*(.+)", block)
            m_protection = re.search(r"Protection Status:\s*(.+)", block)
            m_lock = re.search(r"Lock Status:\s*(.+)", block)
            if m_letter:
                volumes.append(
                    {
                        "volume": m_letter.group(1),
                        "percent_encrypted": float(m_pct.group(1)) if m_pct else None,
                        "conversion_status": m_status.group(1).strip() if m_status else None,
                        "protection_status": m_protection.group(1).strip() if m_protection else None,
                        "lock_status": m_lock.group(1).strip() if m_lock else None,
                    }
                )
        return {"volumes": volumes, "count": len(volumes)}

    def get_status(self, drive_letter: str) -> Dict:
        """Get BitLocker status for a single drive letter, e.g. 'C:'."""
        drive_letter = drive_letter.upper()
        if not drive_letter.endswith(":"):
            drive_letter += ":"
        listed = self.list_volumes()
        if "error" in listed:
            return listed
        for v in listed["volumes"]:
            if v["volume"].upper() == drive_letter:
                return v
        return {"error": f"No volume {drive_letter} found."}

    def enable_encryption(self, drive_letter: str, confirm: bool = False) -> Dict:
        """Turn on BitLocker encryption for a volume, using TPM if available.
        Confirm-gated and needs admin - initial encryption can take a long
        time and uses CPU/disk in the background."""
        drive_letter = drive_letter.upper()
        if not drive_letter.endswith(":"):
            drive_letter += ":"
        if not confirm:
            return {
                "requires_confirmation": True,
                "preview": f"This will start encrypting {drive_letter} with BitLocker (runs in background, may take hours depending on drive size).",
            }
        result = self._run(["manage-bde", "-on", drive_letter, "-RecoveryPassword"])
        if "error" in result:
            return result
        if not result["success"]:
            return {"error": self._admin_hint(result["stderr"] or "manage-bde -on failed")}
        return {"success": True, "volume": drive_letter, "message": "Encryption started - check status for progress."}

    def disable_encryption(self, drive_letter: str, confirm: bool = False) -> Dict:
        """Turn off BitLocker and decrypt a volume. Confirm-gated - this removes
        real protection against offline access to the drive's data."""
        drive_letter = drive_letter.upper()
        if not drive_letter.endswith(":"):
            drive_letter += ":"
        if not confirm:
            return {
                "requires_confirmation": True,
                "preview": f"This will DECRYPT {drive_letter} - if the drive is lost or stolen afterward, its data will no longer be protected.",
            }
        result = self._run(["manage-bde", "-off", drive_letter])
        if "error" in result:
            return result
        if not result["success"]:
            return {"error": self._admin_hint(result["stderr"] or "manage-bde -off failed")}
        return {"success": True, "volume": drive_letter, "message": "Decryption started - check status for progress."}

    def lock_volume(self, drive_letter: str, confirm: bool = False) -> Dict:
        """Lock an encrypted, unlocked volume (data becomes inaccessible until
        unlocked again). Confirm-gated - if it's the boot volume, this can
        make the system unusable at next boot without a recovery key."""
        drive_letter = drive_letter.upper()
        if not drive_letter.endswith(":"):
            drive_letter += ":"
        if not confirm:
            return {
                "requires_confirmation": True,
                "preview": f"This will LOCK {drive_letter} - make sure you have its recovery key before doing this, especially if it's a boot drive.",
            }
        result = self._run(["manage-bde", "-lock", drive_letter])
        if "error" in result:
            return result
        if not result["success"]:
            return {"error": self._admin_hint(result["stderr"] or "manage-bde -lock failed")}
        return {"success": True, "locked_volume": drive_letter}

    def unlock_volume(
        self,
        drive_letter: str,
        password: Optional[str] = None,
        recovery_key: Optional[str] = None,
        confirm: bool = False,
    ) -> Dict:
        """Unlock a locked BitLocker volume using either a password or a
        48-digit recovery key. Confirm-gated since a password/key is passed
        on the command line for this one call."""
        drive_letter = drive_letter.upper()
        if not drive_letter.endswith(":"):
            drive_letter += ":"
        if not confirm:
            return {
                "requires_confirmation": True,
                "preview": f"This will unlock {drive_letter} using the {'recovery key' if recovery_key else 'password'} provided.",
            }
        if recovery_key:
            args = ["manage-bde", "-unlock", drive_letter, "-RecoveryPassword", recovery_key]
        elif password:
            args = ["manage-bde", "-unlock", drive_letter, "-Password", password]
        else:
            return {"error": "Provide either a password or a recovery_key."}
        result = self._run(args)
        if "error" in result:
            return result
        if not result["success"]:
            return {"error": self._admin_hint(result["stderr"] or "manage-bde -unlock failed")}
        return {"success": True, "unlocked_volume": drive_letter}

    def get_recovery_key(self, drive_letter: str, confirm: bool = False) -> Dict:
        """Retrieve the numerical recovery password(s) for a volume. Confirm-gated
        on its own - this reveals a secret capable of decrypting the whole drive."""
        drive_letter = drive_letter.upper()
        if not drive_letter.endswith(":"):
            drive_letter += ":"
        if not confirm:
            return {
                "requires_confirmation": True,
                "preview": f"This will display the BitLocker recovery key for {drive_letter} - anyone with it can decrypt this drive.",
            }
        result = self._run(["manage-bde", "-protectors", "-get", drive_letter])
        if "error" in result:
            return result
        if not result["success"]:
            return {"error": self._admin_hint(result["stderr"] or "manage-bde -protectors failed")}
        keys = re.findall(r"Password:\s*\n\s*([\d-]{50,60})", result["stdout"])
        return {"volume": drive_letter, "recovery_keys": keys or None, "raw": result["stdout"] if not keys else None}
