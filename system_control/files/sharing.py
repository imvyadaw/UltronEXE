"""File Sharing
===============
Windows native SMB network-share control for folders (`net share` /
the SmbShare PowerShell cmdlets) - list/create/remove a share and read
its permissions. This is the OS-level "share this folder on the
network" surface, distinct from apps/cloud/_sync_folder_base.py (which
just locates a *third-party* cloud client's local sync folder, e.g.
Dropbox/OneDrive, so a file can be dropped into it - no network-share
concept there at all).

Creating/removing a share changes what's reachable from other devices
on the network, so both are confirm-gated and need admin, same as
device_manager.py's enable/disable pattern.
"""

import json
import subprocess
from pathlib import Path
from typing import Dict


class FileSharing:
    """List/create/remove native Windows SMB folder shares."""

    def _run_ps(self, cmd: str, timeout: float = 20.0) -> Dict:
        try:
            result = subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", cmd],
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            return {
                "success": result.returncode == 0,
                "stdout": result.stdout.strip(),
                "stderr": result.stderr.strip(),
            }
        except FileNotFoundError:
            return {"error": "PowerShell not found - this is only available on Windows"}
        except subprocess.TimeoutExpired:
            return {"error": "Command timed out"}
        except Exception as e:
            return {"error": str(e)}

    def _admin_hint(self, err: str) -> str:
        if err and ("access" in err.lower() or "denied" in err.lower() or "administrat" in err.lower()):
            return err + " - this needs ULTRON running as Administrator."
        return err

    def list_shares(self) -> Dict:
        """List all current SMB shares on this machine (name, path, description)."""
        cmd = "Get-SmbShare | Select-Object Name,Path,Description,ShareType | ConvertTo-Json"
        result = self._run_ps(cmd)
        if "error" in result:
            return result
        if not result["success"]:
            return {"error": self._admin_hint(result["stderr"] or "Get-SmbShare failed")}
        try:
            data = json.loads(result["stdout"]) if result["stdout"] else []
            shares = data if isinstance(data, list) else [data]
        except Exception as e:
            return {"error": f"Could not parse output: {e}", "raw": result["stdout"]}
        return {"success": True, "shares": shares, "count": len(shares)}

    def get_share_permissions(self, share_name: str) -> Dict:
        """Get the access-control entries for one existing share."""
        if not share_name:
            return {"error": "share_name must be non-empty"}
        safe = share_name.replace("'", "''")
        cmd = f"Get-SmbShareAccess -Name '{safe}' | Select-Object AccountName,AccessControlType,AccessRight | ConvertTo-Json"
        result = self._run_ps(cmd)
        if "error" in result:
            return result
        if not result["success"]:
            return {"error": self._admin_hint(result["stderr"] or f"Share not found: {share_name}")}
        try:
            data = json.loads(result["stdout"]) if result["stdout"] else []
            entries = data if isinstance(data, list) else [data]
        except Exception as e:
            return {"error": f"Could not parse output: {e}", "raw": result["stdout"]}
        return {"success": True, "share_name": share_name, "permissions": entries}

    def share_folder(self, path: str, share_name: str, read_only: bool = True, confirm: bool = False) -> Dict:
        """Share a local folder over the network under share_name. Read-
        only by default (grants Everyone Read); set read_only=False for
        Change access. Needs admin. Confirm-gated - this makes the
        folder reachable from other devices on the network."""
        p = Path(path)
        if not p.exists() or not p.is_dir():
            return {"error": f"Folder not found: {path}"}
        if not share_name:
            return {"error": "share_name must be non-empty"}
        access = "Read" if read_only else "Change"
        if not confirm:
            return {
                "success": False,
                "needs_confirmation": True,
                "preview": f"Would share {p} on the network as {share_name!r} "
                f"(Everyone: {access}) - reachable from other devices. Needs admin.",
                "message": "Call again with confirm=true to apply.",
            }
        safe_name = share_name.replace("'", "''")
        safe_path = str(p).replace("'", "''")
        cmd = (
            f"New-SmbShare -Name '{safe_name}' -Path '{safe_path}' -FullAccess 'Everyone'"
            if not read_only
            else f"New-SmbShare -Name '{safe_name}' -Path '{safe_path}' -ReadAccess 'Everyone'"
        )
        result = self._run_ps(cmd)
        if "error" in result:
            return result
        if not result["success"]:
            return {"error": self._admin_hint(result["stderr"] or "New-SmbShare failed")}
        return {"success": True, "share_name": share_name, "path": str(p), "access": access}

    def unshare_folder(self, share_name: str, confirm: bool = False) -> Dict:
        """Remove a network share (the folder itself is untouched, only
        stops being shared). Needs admin. Confirm-gated."""
        if not share_name:
            return {"error": "share_name must be non-empty"}
        if not confirm:
            return {
                "success": False,
                "needs_confirmation": True,
                "preview": f"Would stop sharing {share_name!r} (needs admin)",
                "message": "Call again with confirm=true to apply.",
            }
        safe = share_name.replace("'", "''")
        cmd = f"Remove-SmbShare -Name '{safe}' -Force"
        result = self._run_ps(cmd)
        if "error" in result:
            return result
        if not result["success"]:
            return {"error": self._admin_hint(result["stderr"] or f"Could not remove share: {share_name}")}
        return {"success": True, "share_name": share_name, "removed": True}
