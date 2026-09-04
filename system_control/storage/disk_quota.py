"""Disk Quota Manager
=====================
Controls NTFS per-user disk quotas via `fsutil quota` - the built-in
Windows client mechanism for limiting how much space individual users
can consume on a volume (Properties > Quota tab on a drive, or the
scriptable equivalent). This is distinct from Windows Server's File
Server Resource Manager (dirquota.exe), which isn't present on client
Windows; fsutil quota is the client-side counterpart and only works
on NTFS volumes.

Distinct from format_manager.py (filesystem type/health of a volume
as a whole) and partition_manager.py (the partition table) - this
module governs per-USER space consumption within an existing NTFS
volume, a layer that only makes sense once a filesystem is already
mounted.

query() and list_violations() are read-only but still typically need
admin, since fsutil quota touches the volume's quota database
directly. enable_tracking, enable_enforcement, disable, and
set_user_quota all change volume-wide or per-user policy and are
confirm-gated - enforcement in particular can start actively blocking
users from writing once their limit is hit.
"""

import subprocess
from typing import Dict


class DiskQuotaManager:
    """Inspect and control NTFS per-user disk quotas via fsutil quota."""

    def _run(self, cmd, timeout: float = 30.0) -> Dict:
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
            return {
                "success": result.returncode == 0,
                "stdout": result.stdout.strip(),
                "stderr": result.stderr.strip(),
            }
        except FileNotFoundError:
            return {"error": "fsutil not found - this is only available on Windows"}
        except subprocess.TimeoutExpired:
            return {"error": "Command timed out"}
        except Exception as e:
            return {"error": str(e)}

    def _admin_hint(self, err: str) -> str:
        if err and ("denied" in err.lower() or "not authorized" in err.lower() or "elevat" in err.lower()):
            return err + " - this needs ULTRON running as Administrator."
        return err

    @staticmethod
    def _vol(volume: str) -> str:
        v = volume.strip().rstrip(":").upper()
        return f"{v}:"

    def query(self, volume: str) -> Dict:
        """Read the quota state (tracking/enforcement on-or-off) and every
        user's current usage and limits on a volume."""
        result = self._run(["fsutil", "quota", "query", self._vol(volume)])
        if "error" in result:
            return result
        if not result["success"]:
            return {"error": self._admin_hint(result["stderr"] or "fsutil quota query failed.")}
        return {"volume": self._vol(volume), "raw_output": result["stdout"]}

    def enable_tracking(self, volume: str, confirm: bool = False) -> Dict:
        """Turn on quota TRACKING for a volume - usage is measured and
        recorded per user, but nobody is blocked from writing. Confirm-
        gated and needs admin."""
        vol = self._vol(volume)
        if not confirm:
            return {
                "requires_confirmation": True,
                "preview": f"This will enable quota tracking (measurement only, no enforcement) on {vol}.",
            }
        result = self._run(["fsutil", "quota", "track", vol])
        if "error" in result:
            return result
        if not result["success"]:
            return {"error": self._admin_hint(result["stderr"] or "fsutil quota track failed.")}
        return {"success": True, "volume": vol, "mode": "tracking"}

    def enable_enforcement(self, volume: str, confirm: bool = False) -> Dict:
        """Turn on quota ENFORCEMENT for a volume - users who exceed their
        configured limit will be blocked from writing more data.
        Confirm-gated, destructive to workflows if limits are too low,
        and needs admin."""
        vol = self._vol(volume)
        if not confirm:
            return {
                "requires_confirmation": True,
                "preview": (
                    f"This will enable quota ENFORCEMENT on {vol} - any user over their configured limit "
                    "will be blocked from writing further data to this volume."
                ),
            }
        result = self._run(["fsutil", "quota", "enforce", vol])
        if "error" in result:
            return result
        if not result["success"]:
            return {"error": self._admin_hint(result["stderr"] or "fsutil quota enforce failed.")}
        return {"success": True, "volume": vol, "mode": "enforcing"}

    def disable(self, volume: str, confirm: bool = False) -> Dict:
        """Turn quotas off entirely for a volume (no tracking, no
        enforcement). Confirm-gated and needs admin."""
        vol = self._vol(volume)
        if not confirm:
            return {
                "requires_confirmation": True,
                "preview": f"This will disable disk quotas entirely on {vol}.",
            }
        result = self._run(["fsutil", "quota", "disable", vol])
        if "error" in result:
            return result
        if not result["success"]:
            return {"error": self._admin_hint(result["stderr"] or "fsutil quota disable failed.")}
        return {"success": True, "volume": vol, "mode": "disabled"}

    def set_user_quota(
        self, volume: str, username: str, warning_bytes: int, limit_bytes: int, confirm: bool = False
    ) -> Dict:
        """Set one user's warning threshold and hard limit on a volume.
        Quota tracking (or enforcement) must already be enabled for this
        to have any effect. Confirm-gated and needs admin."""
        vol = self._vol(volume)
        if warning_bytes > limit_bytes:
            return {"error": "warning_bytes cannot exceed limit_bytes."}
        if not confirm:
            return {
                "requires_confirmation": True,
                "preview": (
                    f"This will set {username}'s quota on {vol} to a {limit_bytes}-byte hard limit "
                    f"with a warning at {warning_bytes} bytes."
                ),
            }
        result = self._run(["fsutil", "quota", "modify", vol, str(warning_bytes), str(limit_bytes), username])
        if "error" in result:
            return result
        if not result["success"]:
            return {"error": self._admin_hint(result["stderr"] or "fsutil quota modify failed.")}
        return {
            "success": True,
            "volume": vol,
            "username": username,
            "warning_bytes": warning_bytes,
            "limit_bytes": limit_bytes,
        }

    def list_violations(self) -> Dict:
        """List all users currently over their quota warning or limit
        threshold, across all volumes with quotas enabled."""
        result = self._run(["fsutil", "quota", "violations"])
        if "error" in result:
            return result
        if not result["success"]:
            return {"error": self._admin_hint(result["stderr"] or "fsutil quota violations failed.")}
        return {"raw_output": result["stdout"]}
