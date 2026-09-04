"""Ransomware Protection Manager
=================================
Controls Windows Defender's "Controlled folder access" feature -
the ransomware-specific protection that blocks unrecognized apps
from modifying files in protected folders. Distinct from
defender_manager.py (general Defender real-time protection/scans/
exclusions, a different Set-MpPreference surface) - this module is
scoped specifically to the controlled-folder-access + allowed-apps
feature set.

Status reads need no admin. Enabling/disabling the feature and
adding/removing protected folders or allowed apps are confirm-gated -
turning this off removes ransomware-specific protection, and an
overly broad allowed-app entry can itself become a bypass.
"""

import subprocess
from typing import Dict


class RansomwareProtection:
    """Inspect and control Windows Defender's Controlled Folder Access."""

    def _run_ps(self, script: str, timeout: float = 30.0) -> Dict:
        try:
            result = subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
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
            return {"error": "powershell not found - this is only available on Windows"}
        except subprocess.TimeoutExpired:
            return {"error": "Command timed out"}
        except Exception as e:
            return {"error": str(e)}

    def _admin_hint(self, err: str) -> str:
        if err and ("denied" in err.lower() or "not authorized" in err.lower() or "elevat" in err.lower()):
            return err + " - this needs ULTRON running as Administrator."
        return err

    def get_status(self) -> Dict:
        """Check whether Controlled Folder Access is enabled (Enabled/Disabled/AuditMode)."""
        result = self._run_ps("(Get-MpPreference).EnableControlledFolderAccess")
        if "error" in result:
            return result
        if not result["success"]:
            return {"error": self._admin_hint(result["stderr"] or "Get-MpPreference failed")}
        raw = result["stdout"].strip()
        mapping = {"0": "Disabled", "1": "Enabled", "2": "AuditMode", "3": "BlockDiskModificationOnly"}
        return {"state": mapping.get(raw, raw), "enabled": raw == "1"}

    def set_enabled(self, enabled: bool, audit_mode: bool = False, confirm: bool = False) -> Dict:
        """Enable or disable Controlled Folder Access. audit_mode=True enables
        it in log-only mode (no actual blocking) for testing. Confirm-gated."""
        if not confirm:
            mode_desc = (
                "audit mode (logs only, doesn't block)"
                if (enabled and audit_mode)
                else ("Enabled" if enabled else "Disabled")
            )
            return {
                "requires_confirmation": True,
                "preview": f"This will set Controlled Folder Access to {mode_desc}."
                + ("" if enabled else " - ransomware-specific folder protection will be OFF."),
            }
        if enabled and audit_mode:
            value = "AuditMode"
        elif enabled:
            value = "Enabled"
        else:
            value = "Disabled"
        result = self._run_ps(f"Set-MpPreference -EnableControlledFolderAccess {value}")
        if "error" in result:
            return result
        if not result["success"]:
            return {"error": self._admin_hint(result["stderr"] or "Set-MpPreference failed")}
        return {"success": True, "state": value}

    def list_protected_folders(self) -> Dict:
        """List folders currently protected by Controlled Folder Access."""
        result = self._run_ps("(Get-MpPreference).ControlledFolderAccessProtectedFolders")
        if "error" in result:
            return result
        if not result["success"]:
            return {"error": self._admin_hint(result["stderr"] or "Get-MpPreference failed")}
        folders = [l.strip() for l in result["stdout"].splitlines() if l.strip()]
        return {"folders": folders, "count": len(folders)}

    def add_protected_folder(self, path: str, confirm: bool = False) -> Dict:
        """Add a folder to the Controlled Folder Access protected list. Confirm-gated
        only because it can trip false-positive blocks for legitimate apps writing there."""
        if not confirm:
            return {
                "requires_confirmation": True,
                "preview": f"This will add '{path}' to ransomware-protected folders - unrecognized apps will be blocked from modifying files there.",
            }
        result = self._run_ps(f"Add-MpPreference -ControlledFolderAccessProtectedFolders '{path}'")
        if "error" in result:
            return result
        if not result["success"]:
            return {"error": self._admin_hint(result["stderr"] or "Add-MpPreference failed")}
        return {"success": True, "protected_folder": path}

    def remove_protected_folder(self, path: str, confirm: bool = False) -> Dict:
        """Remove a folder from the Controlled Folder Access protected list. Confirm-gated."""
        if not confirm:
            return {"requires_confirmation": True, "preview": f"This will remove ransomware protection from '{path}'."}
        result = self._run_ps(f"Remove-MpPreference -ControlledFolderAccessProtectedFolders '{path}'")
        if "error" in result:
            return result
        if not result["success"]:
            return {"error": self._admin_hint(result["stderr"] or "Remove-MpPreference failed")}
        return {"success": True, "removed_folder": path}

    def list_allowed_apps(self) -> Dict:
        """List apps allowed to modify files in protected folders."""
        result = self._run_ps("(Get-MpPreference).ControlledFolderAccessAllowedApplications")
        if "error" in result:
            return result
        if not result["success"]:
            return {"error": self._admin_hint(result["stderr"] or "Get-MpPreference failed")}
        apps = [l.strip() for l in result["stdout"].splitlines() if l.strip()]
        return {"allowed_apps": apps, "count": len(apps)}

    def add_allowed_app(self, exe_path: str, confirm: bool = False) -> Dict:
        """Allow a specific app (by exe path) to bypass Controlled Folder Access.
        Confirm-gated - an overly broad allow entry can itself become a
        ransomware bypass, so this should only be used for a known-legitimate
        app that's being wrongly blocked."""
        if not confirm:
            return {
                "requires_confirmation": True,
                "preview": f"This will allow '{exe_path}' to modify files in protected folders, "
                f"bypassing ransomware protection for that app specifically.",
            }
        result = self._run_ps(f"Add-MpPreference -ControlledFolderAccessAllowedApplications '{exe_path}'")
        if "error" in result:
            return result
        if not result["success"]:
            return {"error": self._admin_hint(result["stderr"] or "Add-MpPreference failed")}
        return {"success": True, "allowed_app": exe_path}

    def remove_allowed_app(self, exe_path: str, confirm: bool = False) -> Dict:
        """Remove a previously allowed app's bypass. Confirm-gated."""
        if not confirm:
            return {
                "requires_confirmation": True,
                "preview": f"This will revoke '{exe_path}'s bypass of Controlled Folder Access.",
            }
        result = self._run_ps(f"Remove-MpPreference -ControlledFolderAccessAllowedApplications '{exe_path}'")
        if "error" in result:
            return result
        if not result["success"]:
            return {"error": self._admin_hint(result["stderr"] or "Remove-MpPreference failed")}
        return {"success": True, "removed_app": exe_path}
