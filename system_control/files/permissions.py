"""File Permissions
===================
Windows file/folder permissions (NTFS ACLs) and the basic read-only
attribute: inspect who has what access, grant/remove access for a
user, take ownership, and toggle the read-only attribute - the
`icacls`/`attrib`/`takeown` surface, distinct from core/permissions.py
(which is ULTRON's own internal confirm-gate registry for which *tools*
count as destructive, not a filesystem-ACL tool itself).

All ACL-changing methods are confirm-gated; take_ownership and granting
Full/Modify rights can lock the current user out of a file if misused,
so previews spell out exactly what will change.
"""

import subprocess
from pathlib import Path
from typing import Dict

_VALID_RIGHTS = {"read", "write", "modify", "full", "read_execute"}
_RIGHTS_MAP = {
    "read": "R",
    "write": "W",
    "modify": "M",
    "full": "F",
    "read_execute": "RX",
}


class FilePermissions:
    """Inspect/grant/remove NTFS permissions, take ownership, toggle read-only."""

    def _run(self, args: list, timeout: float = 20.0) -> Dict:
        try:
            result = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
            return {
                "success": result.returncode == 0,
                "stdout": result.stdout.strip(),
                "stderr": result.stderr.strip(),
            }
        except FileNotFoundError:
            return {"error": f"{args[0]} not found - this is only available on Windows"}
        except subprocess.TimeoutExpired:
            return {"error": "Command timed out"}
        except Exception as e:
            return {"error": str(e)}

    def _admin_hint(self, err: str) -> str:
        if err and ("access" in err.lower() or "denied" in err.lower()):
            return err + " - this may need ULTRON running as Administrator."
        return err

    def get_permissions(self, path: str) -> Dict:
        """List the current ACL entries for a file or folder (icacls)."""
        p = Path(path)
        if not p.exists():
            return {"error": f"Path not found: {path}"}
        result = self._run(["icacls", str(p)])
        if "error" in result:
            return result
        if not result["success"]:
            return {"error": self._admin_hint(result["stderr"] or "icacls failed")}
        return {"success": True, "path": str(p), "acl": result["stdout"]}

    def set_permission(self, path: str, user: str, rights: str, confirm: bool = False) -> Dict:
        """Grant a user/group a permission level (read/write/modify/full/
        read_execute) on a file or folder. Confirm-gated - granting
        'full' to the wrong account is a real security risk, and
        removing your own access is possible if user is wrong."""
        p = Path(path)
        if not p.exists():
            return {"error": f"Path not found: {path}"}
        if not user:
            return {"error": "user must be non-empty (e.g. a Windows username or 'Everyone')"}
        rights_key = (rights or "").lower()
        if rights_key not in _VALID_RIGHTS:
            return {"error": f"rights must be one of {sorted(_VALID_RIGHTS)}"}
        if not confirm:
            return {
                "success": False,
                "needs_confirmation": True,
                "preview": f"Would grant {user!r} {rights} access to {p}",
                "message": "Call again with confirm=true to apply.",
            }
        icacls_right = _RIGHTS_MAP[rights_key]
        result = self._run(["icacls", str(p), "/grant", f"{user}:{icacls_right}"])
        if "error" in result:
            return result
        if not result["success"]:
            return {"error": self._admin_hint(result["stderr"] or "icacls /grant failed")}
        return {"success": True, "path": str(p), "user": user, "rights": rights_key}

    def remove_permission(self, path: str, user: str, confirm: bool = False) -> Dict:
        """Remove all explicit permission entries for a user/group from a
        file or folder's ACL. Confirm-gated."""
        p = Path(path)
        if not p.exists():
            return {"error": f"Path not found: {path}"}
        if not user:
            return {"error": "user must be non-empty"}
        if not confirm:
            return {
                "success": False,
                "needs_confirmation": True,
                "preview": f"Would remove {user!r}'s permissions from {p}",
                "message": "Call again with confirm=true to apply.",
            }
        result = self._run(["icacls", str(p), "/remove", user])
        if "error" in result:
            return result
        if not result["success"]:
            return {"error": self._admin_hint(result["stderr"] or "icacls /remove failed")}
        return {"success": True, "path": str(p), "user": user, "removed": True}

    def take_ownership(self, path: str, recursive: bool = False, confirm: bool = False) -> Dict:
        """Take ownership of a file or folder as the current user
        (takeown /f). Needs admin for files owned by another account.
        Confirm-gated."""
        p = Path(path)
        if not p.exists():
            return {"error": f"Path not found: {path}"}
        if not confirm:
            scope = " (recursively)" if recursive else ""
            return {
                "success": False,
                "needs_confirmation": True,
                "preview": f"Would take ownership of {p}{scope} (needs admin for files you don't own)",
                "message": "Call again with confirm=true to apply.",
            }
        args = ["takeown", "/f", str(p)]
        if recursive:
            args.append("/r")
            args.append("/d")
            args.append("y")
        result = self._run(args)
        if "error" in result:
            return result
        if not result["success"]:
            return {"error": self._admin_hint(result["stderr"] or "takeown failed")}
        return {"success": True, "path": str(p), "recursive": recursive}

    def make_read_only(self, path: str, confirm: bool = False) -> Dict:
        """Set the read-only attribute on a file. Confirm-gated."""
        return self._toggle_read_only(path, read_only=True, confirm=confirm)

    def remove_read_only(self, path: str, confirm: bool = False) -> Dict:
        """Clear the read-only attribute on a file. Confirm-gated."""
        return self._toggle_read_only(path, read_only=False, confirm=confirm)

    def _toggle_read_only(self, path: str, read_only: bool, confirm: bool) -> Dict:
        p = Path(path)
        if not p.exists():
            return {"error": f"Path not found: {path}"}
        action = "set" if read_only else "clear"
        if not confirm:
            return {
                "success": False,
                "needs_confirmation": True,
                "preview": f"Would {action} the read-only attribute on {p}",
                "message": "Call again with confirm=true to apply.",
            }
        flag = "+r" if read_only else "-r"
        result = self._run(["attrib", flag, str(p)])
        if "error" in result:
            return result
        if not result["success"]:
            return {"error": self._admin_hint(result["stderr"] or "attrib failed")}
        return {"success": True, "path": str(p), "read_only": read_only}
