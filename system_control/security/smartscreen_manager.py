"""SmartScreen Manager
======================
Reads and controls the three independent Windows SmartScreen surfaces:

  1. "Check apps and files" (Explorer) - warns before running unrecognized
     downloaded executables. Registry: HKLM\\SOFTWARE\\Microsoft\\Windows\\
     CurrentVersion\\Policies\\System, SmartScreenEnabled (string:
     "Warn" | "RequireAdmin" | "Off").
  2. Store apps' web-content evaluation - HKLM\\SOFTWARE\\Microsoft\\
     Windows\\CurrentVersion\\AppHost, EnableWebContentEvaluation (DWORD).
  3. Microsoft Edge SmartScreen (phishing/malware site + download
     reputation checks) and its Potentially-Unwanted-App blocking -
     HKLM\\SOFTWARE\\Policies\\Microsoft\\Edge, SmartScreenEnabled /
     SmartScreenPuaEnabled (DWORD, machine policy).

Distinct from system_control/security/defender_manager.py (Defender's
own real-time file scanning engine) and from exploit_protection.py
(process-level memory-safety mitigations) - SmartScreen is reputation/
network-based checking of files and sites, not signature scanning or
process mitigation.

All reads are plain and need no admin. Every setter here reduces (when
turning something off) or restores (when turning it on) a layer of
protection against downloaded malware and phishing sites, so every
setter is confirm-gated and needs admin.
"""

import json
import subprocess
from typing import Dict


class SmartScreenManager:
    """Inspect and control Windows SmartScreen across Explorer, Store apps, and Edge."""

    _EXPLORER_KEY = r"HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\System"
    _APPHOST_KEY = r"HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\AppHost"
    _EDGE_KEY = r"HKLM\SOFTWARE\Policies\Microsoft\Edge"

    _EXPLORER_LEVELS = ("Warn", "RequireAdmin", "Off")

    def _run_ps(self, script: str, timeout: float = 20.0) -> Dict:
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
        if err and ("denied" in err.lower() or "elevat" in err.lower() or "access is denied" in err.lower()):
            return err + " - this needs ULTRON running as Administrator."
        return err

    def _read_value(self, key: str, name: str) -> Dict:
        script = f'(Get-ItemProperty -Path "Registry::{key}" -Name {name} -ErrorAction SilentlyContinue).{name} | ConvertTo-Json'
        result = self._run_ps(script)
        if "error" in result:
            return result
        if not result["success"]:
            return {"error": self._admin_hint(result["stderr"] or f"Could not read {name}.")}
        raw = result["stdout"]
        if not raw:
            return {"value": None}
        try:
            return {"value": json.loads(raw)}
        except Exception:
            return {"value": raw.strip('"')}

    def get_status(self) -> Dict:
        """One-call snapshot of all three SmartScreen surfaces: Explorer's
        check-apps-and-files level, Store apps' web content evaluation,
        and Edge's SmartScreen + PUA blocking (Edge values only present
        if a machine policy has set them - Edge otherwise manages its
        own setting internally and won't show here)."""
        explorer = self._read_value(self._EXPLORER_KEY, "SmartScreenEnabled")
        apphost = self._read_value(self._APPHOST_KEY, "EnableWebContentEvaluation")
        edge_screen = self._read_value(self._EDGE_KEY, "SmartScreenEnabled")
        edge_pua = self._read_value(self._EDGE_KEY, "SmartScreenPuaEnabled")
        return {
            "explorer_check_apps_and_files": explorer.get("value") if "error" not in explorer else explorer,
            "store_apps_web_content_evaluation_enabled": (
                bool(apphost.get("value")) if "error" not in apphost and apphost.get("value") is not None else None
            ),
            "edge_smartscreen_policy": edge_screen.get("value") if "error" not in edge_screen else None,
            "edge_pua_blocking_policy": (
                bool(edge_pua.get("value")) if "error" not in edge_pua and edge_pua.get("value") is not None else None
            ),
            "note": "Edge fields are null unless a machine policy has been set for Edge specifically; "
            "Edge otherwise controls its own SmartScreen toggle in edge://settings.",
        }

    def set_explorer_smartscreen(self, level: str, confirm: bool = False) -> Dict:
        """Set the Explorer "check apps and files" level: 'Warn' (default,
        warns before running), 'RequireAdmin' (warns and needs an admin
        to bypass), or 'Off' (no check at all - unrecognized downloaded
        executables run silently). Confirm-gated, needs admin."""
        if level not in self._EXPLORER_LEVELS:
            return {"error": f"level must be one of {self._EXPLORER_LEVELS}."}
        if not confirm:
            preview = f"This will set 'Check apps and files' SmartScreen to '{level}'."
            if level == "Off":
                preview += " Windows will no longer warn before running unrecognized downloaded executables."
            return {"requires_confirmation": True, "preview": preview}
        script = (
            f'Set-ItemProperty -Path "Registry::{self._EXPLORER_KEY}" '
            f"-Name SmartScreenEnabled -Value '{level}' -Type String -Force"
        )
        result = self._run_ps(script)
        if "error" in result:
            return result
        if not result["success"]:
            return {"error": self._admin_hint(result["stderr"] or "Failed to set SmartScreenEnabled.")}
        return {"success": True, "explorer_check_apps_and_files": level}

    def set_store_apps_smartscreen(self, enabled: bool, confirm: bool = False) -> Dict:
        """Enable/disable web content evaluation for Microsoft Store apps
        (checks URLs those apps open against SmartScreen's reputation
        service). Confirm-gated, needs admin."""
        if not confirm:
            return {
                "requires_confirmation": True,
                "preview": f"This will turn {'ON' if enabled else 'OFF'} SmartScreen web content evaluation for Store apps.",
            }
        script = (
            f'Set-ItemProperty -Path "Registry::{self._APPHOST_KEY}" '
            f"-Name EnableWebContentEvaluation -Value {1 if enabled else 0} -Type DWord -Force"
        )
        result = self._run_ps(script)
        if "error" in result:
            return result
        if not result["success"]:
            return {"error": self._admin_hint(result["stderr"] or "Failed to set EnableWebContentEvaluation.")}
        return {"success": True, "store_apps_web_content_evaluation_enabled": enabled}

    def set_edge_smartscreen(self, enabled: bool, confirm: bool = False) -> Dict:
        """Set a machine policy forcing Edge's SmartScreen (phishing/
        malware site + download reputation checks) on or off, overriding
        the per-user toggle in edge://settings. Confirm-gated, needs
        admin; Edge must restart to pick it up."""
        if not confirm:
            preview = f"This will set a machine POLICY forcing Edge SmartScreen {'ON' if enabled else 'OFF'}, overriding the per-user setting."
            if not enabled:
                preview += " Edge will stop warning about phishing sites and unsafe downloads."
            return {"requires_confirmation": True, "preview": preview}
        script = (
            f'New-Item -Path "Registry::{self._EDGE_KEY}" -Force | Out-Null; '
            f'Set-ItemProperty -Path "Registry::{self._EDGE_KEY}" '
            f"-Name SmartScreenEnabled -Value {1 if enabled else 0} -Type DWord -Force"
        )
        result = self._run_ps(script)
        if "error" in result:
            return result
        if not result["success"]:
            return {"error": self._admin_hint(result["stderr"] or "Failed to set Edge SmartScreenEnabled policy.")}
        return {"success": True, "edge_smartscreen_policy": enabled, "note": "Restart Edge to apply."}

    def set_edge_pua_blocking(self, enabled: bool, confirm: bool = False) -> Dict:
        """Set a machine policy for Edge's Potentially-Unwanted-Application
        (PUA) blocking. Confirm-gated, needs admin; Edge must restart."""
        if not confirm:
            return {
                "requires_confirmation": True,
                "preview": f"This will set a machine POLICY forcing Edge's PUA blocking {'ON' if enabled else 'OFF'}.",
            }
        script = (
            f'New-Item -Path "Registry::{self._EDGE_KEY}" -Force | Out-Null; '
            f'Set-ItemProperty -Path "Registry::{self._EDGE_KEY}" '
            f"-Name SmartScreenPuaEnabled -Value {1 if enabled else 0} -Type DWord -Force"
        )
        result = self._run_ps(script)
        if "error" in result:
            return result
        if not result["success"]:
            return {"error": self._admin_hint(result["stderr"] or "Failed to set Edge SmartScreenPuaEnabled policy.")}
        return {"success": True, "edge_pua_blocking_policy": enabled, "note": "Restart Edge to apply."}

    def clear_edge_policy(self, confirm: bool = False) -> Dict:
        """Remove the machine-policy overrides this manager may have set
        for Edge, returning control to the per-user edge://settings
        toggle. Confirm-gated, needs admin."""
        if not confirm:
            return {
                "requires_confirmation": True,
                "preview": "This will remove the Edge SmartScreen/PUA machine policy overrides, returning control to the user's own edge://settings toggle.",
            }
        script = (
            f'Remove-ItemProperty -Path "Registry::{self._EDGE_KEY}" -Name SmartScreenEnabled -ErrorAction SilentlyContinue; '
            f'Remove-ItemProperty -Path "Registry::{self._EDGE_KEY}" -Name SmartScreenPuaEnabled -ErrorAction SilentlyContinue'
        )
        result = self._run_ps(script)
        if "error" in result:
            return result
        if not result["success"]:
            return {"error": self._admin_hint(result["stderr"] or "Failed to clear Edge policy values.")}
        return {"success": True, "cleared": ["SmartScreenEnabled", "SmartScreenPuaEnabled"]}
