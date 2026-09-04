"""Network Drives Manager
==========================
Mapped-network-drive control via `net use` - list currently mapped
drives/UNC connections, map a new drive letter to a UNC path (with
optional credentials and persistence across reboots), and disconnect
one. Distinct from system_control/files (local filesystem operations)
and from the top-level networking/ package (ssh/ftp protocol clients)
- this only manages the Windows drive-letter <-> UNC-path mappings
`net use` itself owns.

Listing mapped drives is a plain read. Mapping/unmapping a drive is
confirm-gated as state-changing, and mapping with a password is
flagged in the preview since the credential is passed on the command
line for that one call.
"""

import subprocess
import re
from typing import Dict, Optional


class NetworkDrives:
    """Inspect and control mapped network drives via `net use`."""

    def _run(self, args: list, timeout: float = 20.0) -> Dict:
        try:
            result = subprocess.run(["net"] + args, capture_output=True, text=True, timeout=timeout)
            return {
                "success": result.returncode == 0,
                "stdout": result.stdout.strip(),
                "stderr": result.stderr.strip(),
            }
        except FileNotFoundError:
            return {"error": "net not found - this is only available on Windows"}
        except subprocess.TimeoutExpired:
            return {"error": "Command timed out"}
        except Exception as e:
            return {"error": str(e)}

    def _admin_hint(self, err: str) -> str:
        if err and ("denied" in err.lower() or "not authorized" in err.lower()):
            return err + " - check credentials, or this may need ULTRON running as Administrator."
        return err

    def list_mapped_drives(self) -> Dict:
        """List currently mapped network drives (letter, UNC path, connection status)."""
        result = self._run(["use"])
        if "error" in result:
            return result
        if not result["success"]:
            return {"error": self._admin_hint(result["stderr"] or "net use failed")}
        drives = []
        for line in result["stdout"].splitlines():
            m = re.match(r"^(OK|Disconnected|Unavailable)\s+([A-Z]:)\s+(\S.*?)\s*(Microsoft.*)?$", line.strip())
            if m:
                drives.append(
                    {
                        "status": m.group(1),
                        "drive_letter": m.group(2),
                        "unc_path": m.group(3).strip(),
                    }
                )
        return {"drives": drives, "count": len(drives)}

    def get_drive_status(self, drive_letter: str) -> Dict:
        """Get the status/UNC path for a single mapped drive letter, e.g. 'Z:'."""
        drive_letter = drive_letter.upper()
        if not drive_letter.endswith(":"):
            drive_letter += ":"
        listed = self.list_mapped_drives()
        if "error" in listed:
            return listed
        for d in listed["drives"]:
            if d["drive_letter"] == drive_letter:
                return d
        return {"error": f"No mapped drive at {drive_letter}."}

    def map_drive(
        self,
        drive_letter: str,
        unc_path: str,
        username: Optional[str] = None,
        password: Optional[str] = None,
        persistent: bool = True,
        confirm: bool = False,
    ) -> Dict:
        """Map a drive letter (e.g. 'Z:') to a UNC path (e.g. '\\\\server\\share').
        Confirm-gated; if a password is supplied it's flagged in the preview since
        it's passed as a one-off command-line argument to `net use`."""
        drive_letter = drive_letter.upper()
        if not drive_letter.endswith(":"):
            drive_letter += ":"
        if not confirm:
            preview = f"This will map {drive_letter} to '{unc_path}'" + (
                " (persistent across reboots)." if persistent else " (this session only)."
            )
            if password:
                preview += " A password will be passed for this connection."
            return {"requires_confirmation": True, "preview": preview}
        args = ["use", drive_letter, unc_path]
        if password is not None:
            args.append(password)
        if username:
            args += ["/user:" + username]
        args.append("/persistent:yes" if persistent else "/persistent:no")
        result = self._run(args)
        if "error" in result:
            return result
        if not result["success"]:
            return {"error": self._admin_hint(result["stderr"] or "net use mapping failed")}
        return {"success": True, "drive_letter": drive_letter, "unc_path": unc_path, "persistent": persistent}

    def unmap_drive(self, drive_letter: str, confirm: bool = False) -> Dict:
        """Disconnect a mapped network drive by letter. Confirm-gated."""
        drive_letter = drive_letter.upper()
        if not drive_letter.endswith(":"):
            drive_letter += ":"
        if not confirm:
            return {"requires_confirmation": True, "preview": f"This will disconnect mapped drive {drive_letter}."}
        result = self._run(["use", drive_letter, "/delete", "/y"])
        if "error" in result:
            return result
        if not result["success"]:
            return {"error": self._admin_hint(result["stderr"] or "net use /delete failed")}
        return {"success": True, "unmapped": drive_letter}

    def unmap_all(self, confirm: bool = False) -> Dict:
        """Disconnect every currently mapped network drive. Confirm-gated."""
        if not confirm:
            listed = self.list_mapped_drives()
            count = listed.get("count", "an unknown number of") if "error" not in listed else "an unknown number of"
            return {
                "requires_confirmation": True,
                "preview": f"This will disconnect all ({count}) mapped network drives.",
            }
        result = self._run(["use", "*", "/delete", "/y"])
        if "error" in result:
            return result
        if not result["success"]:
            return {"error": self._admin_hint(result["stderr"] or "net use * /delete failed")}
        return {"success": True, "message": "All mapped drives disconnected."}
