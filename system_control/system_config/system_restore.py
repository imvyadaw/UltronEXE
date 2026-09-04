"""System Restore
=================
Windows System Restore control: list/create restore points, restore
the system to a prior point, and enable/disable protection on a
drive - the actual "roll the OS back" surface that
system_properties.py's get_system_protection_status() only reads a
summary of.

Every write here is confirm-gated the same way as the rest of this
package. restore_to_point is the most destructive method in the whole
system_control package - it reboots the machine and reverts system
files/registry/installed programs to the chosen point (user files are
not touched, but installed-since-then programs are removed) - so its
preview is extra explicit about that, and it is blocked outright
unless the caller has already confirmed.

Like device_manager.py/system_properties.py, everything shells out to
PowerShell; Checkpoint-Computer/Restore-Computer/Enable-ComputerRestore/
Disable-ComputerRestore all need ULTRON running as Administrator.
"""

import json
import subprocess
from typing import Dict


class SystemRestore:
    """List/create/restore System Restore points; enable/disable protection."""

    def _run_ps(self, cmd: str, timeout: float = 60.0) -> Dict:
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
            return {"error": f"Command timed out after {timeout}s"}
        except Exception as e:
            return {"error": str(e)}

    def _admin_hint(self, err: str) -> str:
        if err and ("access" in err.lower() or "denied" in err.lower() or "administrat" in err.lower()):
            return err + " - this needs ULTRON running as Administrator."
        return err

    def list_restore_points(self) -> Dict:
        """List all available System Restore points (sequence number, description, time, type)."""
        cmd = (
            "Get-ComputerRestorePoint | Select-Object SequenceNumber,Description,"
            "CreationTime,RestorePointType | ConvertTo-Json"
        )
        result = self._run_ps(cmd)
        if "error" in result:
            return result
        if not result["success"]:
            return {"error": self._admin_hint(result["stderr"] or "Get-ComputerRestorePoint failed")}
        try:
            data = json.loads(result["stdout"]) if result["stdout"] else []
            points = data if isinstance(data, list) else [data]
        except Exception as e:
            return {"error": f"Could not parse output: {e}", "raw": result["stdout"]}
        return {"success": True, "restore_points": points, "count": len(points)}

    def create_restore_point(self, description: str = "ULTRON checkpoint", confirm: bool = False) -> Dict:
        """Create a new System Restore point. Needs admin. Confirm-gated
        (still relatively safe - it only adds a point, doesn't change
        current state - but every state-changing call in this package
        previews first for consistency)."""
        if not confirm:
            return {
                "success": False,
                "needs_confirmation": True,
                "preview": f"Would create a System Restore point named {description!r} (needs admin)",
                "message": "Call again with confirm=true to apply.",
            }
        safe_desc = description.replace("'", "''")
        cmd = f"Checkpoint-Computer -Description '{safe_desc}' -RestorePointType 'MODIFY_SETTINGS'"
        result = self._run_ps(cmd)
        if "error" in result:
            return result
        if not result["success"]:
            return {"error": self._admin_hint(result["stderr"] or "Checkpoint-Computer failed")}
        return {"success": True, "description": description}

    def restore_to_point(self, sequence_number: int, confirm: bool = False) -> Dict:
        """Restore the system to a prior restore point (by SequenceNumber,
        from list_restore_points). DESTRUCTIVE: reboots the machine
        immediately and reverts system files/registry/installed programs
        to that point (personal files are not touched, but anything
        installed since then is removed). Needs admin. Confirm-gated -
        the preview spells out exactly what this does since it cannot be
        undone except by restoring to yet another point."""
        if not isinstance(sequence_number, int):
            return {"error": "sequence_number must be an integer (see list_restore_points)"}
        if not confirm:
            return {
                "success": False,
                "needs_confirmation": True,
                "preview": (
                    f"Would restore the system to restore point #{sequence_number}. "
                    "This REBOOTS the machine immediately and reverts system files, the "
                    "registry, and installed programs to that point - personal files are "
                    "kept, but anything installed since then is removed. This cannot be "
                    "undone except by restoring to another point afterward."
                ),
                "message": "Call again with confirm=true only once the user has explicitly agreed.",
            }
        cmd = f"Restore-Computer -RestorePoint {int(sequence_number)} -Confirm:$false"
        result = self._run_ps(cmd, timeout=30.0)
        if "error" in result:
            return result
        if not result["success"]:
            return {"error": self._admin_hint(result["stderr"] or "Restore-Computer failed")}
        return {
            "success": True,
            "sequence_number": sequence_number,
            "note": "Restore initiated - the machine will reboot to apply it.",
        }

    def get_protection_status(self, drive: str = "C:") -> Dict:
        """Whether System Restore protection is currently on for a drive."""
        safe_drive = drive.replace("'", "''")
        cmd = (
            f"$cfg = Get-CimInstance -Namespace root/default -ClassName SystemRestoreConfig "
            f"-ErrorAction SilentlyContinue; "
            f"$vss = vssadmin list volumes 2>$null | Out-String; "
            f"[PSCustomObject]@{{ Drive='{safe_drive}'; RestoreConfigFound=[bool]$cfg }} | ConvertTo-Json"
        )
        result = self._run_ps(cmd)
        if "error" in result:
            return result
        if not result["success"]:
            return {"error": self._admin_hint(result["stderr"] or "Could not read protection status")}
        try:
            status = json.loads(result["stdout"]) if result["stdout"] else {}
        except Exception as e:
            return {"error": f"Could not parse output: {e}", "raw": result["stdout"]}
        return {"success": True, "drive": drive, "status": status}

    def enable_protection(self, drive: str = "C:", confirm: bool = False) -> Dict:
        """Turn System Restore protection ON for a drive. Needs admin. Confirm-gated."""
        return self._toggle_protection(drive, enable=True, confirm=confirm)

    def disable_protection(self, drive: str = "C:", confirm: bool = False) -> Dict:
        """Turn System Restore protection OFF for a drive (no new restore
        points will be created until re-enabled). Needs admin. Confirm-gated."""
        return self._toggle_protection(drive, enable=False, confirm=confirm)

    def _toggle_protection(self, drive: str, enable: bool, confirm: bool) -> Dict:
        if not drive:
            return {"error": "drive must be non-empty, e.g. 'C:'"}
        action = "enable" if enable else "disable"
        if not confirm:
            return {
                "success": False,
                "needs_confirmation": True,
                "preview": f"Would {action} System Restore protection on {drive} (needs admin)",
                "message": "Call again with confirm=true to apply.",
            }
        safe_drive = drive.replace("'", "''")
        verb = "Enable-ComputerRestore" if enable else "Disable-ComputerRestore"
        cmd = f"{verb} -Drive '{safe_drive}'"
        result = self._run_ps(cmd)
        if "error" in result:
            return result
        if not result["success"]:
            return {"error": self._admin_hint(result["stderr"] or f"{verb} failed")}
        return {"success": True, "drive": drive, "action": action}
