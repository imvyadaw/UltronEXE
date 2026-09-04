"""Office Control
=================
OS-level Microsoft Office *suite* management - distinct from
apps/office/*.py (word.py, excel.py, powerpoint.py, outlook.py,
teams.py, onenote.py, access.py), which each drive a single already-
open app instance via pyautogui (open a file, save, print, ...). This
module instead operates on the Click-to-Run installation as a whole:
which suite/apps are actually installed, what update channel it's on,
and bulk process actions across every Office app at once.

Reads the Click-to-Run configuration registry hive directly
(HKLM\\SOFTWARE\\Microsoft\\Office\\ClickToRun\\Configuration) rather
than shelling to an Office cmdlet, since Office ships no first-class
PowerShell module for this - OfficeC2RClient.exe is only invoked for
the one write path (changing update channel) that has no registry-
only equivalent.
"""
import logging

import os
import subprocess
import winreg
from typing import Dict, List, Optional

# exe name -> friendly name, for install detection and bulk close.
_OFFICE_PROCESSES = {
    "winword.exe": "Word",
    "excel.exe": "Excel",
    "powerpnt.exe": "PowerPoint",
    "outlook.exe": "Outlook",
    "msaccess.exe": "Access",
    "onenote.exe": "OneNote",
    "ms-teams.exe": "Teams",
}

_UPDATE_CHANNELS = {
    "current": "https://officecdn.microsoft.com/pr/492350f6-3a01-4f97-b9c0-c7c6ddf67d60",
    "monthly_enterprise": "https://officecdn.microsoft.com/pr/55336b82-a18d-4dd6-b5f6-9e5095c314a6",
    "semi_annual": "https://officecdn.microsoft.com/pr/7ffbc6bf-bc32-4f92-8982-f9dd17fd3114",
    "semi_annual_preview": "https://officecdn.microsoft.com/pr/b8f9b850-328d-4355-9145-c59439a0c4cf",
    "beta": "https://officecdn.microsoft.com/pr/5440fd1f-7ecb-4221-8110-145efaa6372f",
}


class OfficeControl:
    """Office Click-to-Run install info, update channel, and bulk
    process actions across every Office app."""

    _CONFIG_PATH = r"SOFTWARE\Microsoft\Office\ClickToRun\Configuration"

    def _run_ps(self, script: str, timeout: float = 20.0) -> Dict:
        try:
            result = subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            return {"success": result.returncode == 0, "stdout": result.stdout.strip(), "stderr": result.stderr.strip()}
        except FileNotFoundError:
            return {"error": "powershell not found - this is only available on Windows"}
        except subprocess.TimeoutExpired:
            return {"error": "Command timed out"}
        except Exception as e:
            return {"error": str(e)}

    def get_office_install_info(self) -> Dict:
        """Read Click-to-Run version, platform (32/64-bit), and
        install path from the registry. Returns installed: False if
        Office isn't installed via Click-to-Run (e.g. MSI/volume-
        licensed builds use a different, unsupported hive). No admin
        needed."""
        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, self._CONFIG_PATH) as key:

                def _read(name: str) -> Optional[str]:
                    try:
                        value, _ = winreg.QueryValueEx(key, name)
                        return value
                    except FileNotFoundError:
                        return None

                return {
                    "installed": True,
                    "version": _read("VersionToReport"),
                    "platform": _read("Platform"),
                    "install_path": _read("InstallationPath"),
                    "product_ids": _read("ProductReleaseIds"),
                    "update_channel_url": _read("UpdateChannel") or _read("CDNBaseUrl"),
                }
        except FileNotFoundError:
            return {"installed": False}
        except OSError as e:
            return {"error": str(e)}

    def list_installed_office_apps(self) -> Dict:
        """List which individual Office apps have a resolvable exe on
        this machine (via the App Paths registry). No admin needed."""
        found: List[Dict] = []
        for exe, friendly in _OFFICE_PROCESSES.items():
            path = None
            try:
                with winreg.OpenKey(
                    winreg.HKEY_LOCAL_MACHINE,
                    rf"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\{exe}",
                ) as key:
                    path, _ = winreg.QueryValueEx(key, "")
            except FileNotFoundError:
                logging.getLogger(__name__).exception("Suppressed FileNotFoundError")
            if path and os.path.isfile(path):
                found.append({"app": friendly, "exe": exe, "path": path})
        return {"apps": found, "count": len(found)}

    def set_update_channel(self, channel: str, confirm: bool = False) -> Dict:
        """Switch the Click-to-Run update channel (one of
        _UPDATE_CHANNELS: current, monthly_enterprise, semi_annual,
        semi_annual_preview, beta) and trigger an immediate update
        check via OfficeC2RClient.exe. Confirm-gated, admin-required -
        changes which builds this machine receives going forward, and
        can trigger a large download."""
        if channel not in _UPDATE_CHANNELS:
            return {"error": f"Unknown channel '{channel}'. Known: {sorted(_UPDATE_CHANNELS)}"}
        if not confirm:
            return {
                "requires_confirmation": True,
                "preview": f"This will switch Office's update channel to '{channel}' and check for updates now.",
            }
        info = self.get_office_install_info()
        install_path = info.get("install_path") if info.get("installed") else None
        client = os.path.join(
            install_path or r"C:\Program Files\Common Files\Microsoft Shared\ClickToRun", "OfficeC2RClient.exe"
        )
        if not os.path.isfile(client):
            return {"error": "OfficeC2RClient.exe not found - Office may not be Click-to-Run installed."}
        url = _UPDATE_CHANNELS[channel]
        result = self._run_ps(
            f"Start-Process -FilePath '{client}' -ArgumentList "
            f"'/changesetting Channel={url} /update user' -Wait -PassThru | Out-Null; 'ok'"
        )
        if "error" in result:
            return result
        if not result["success"]:
            return {
                "error": result["stderr"] or "Channel change failed.",
                "admin_hint": "Re-run elevated if this failed.",
            }
        return {"success": True, "channel": channel}

    def close_all_office_apps(self, confirm: bool = False) -> Dict:
        """Force-close every running Office app process. Confirm-gated
        - unsaved changes in open documents are lost, no save prompt."""
        if not confirm:
            return {
                "requires_confirmation": True,
                "preview": "This will force-close every running Office app (Word, Excel, PowerPoint, Outlook, Access, OneNote, Teams). Unsaved changes will be lost.",
            }
        closed = []
        for exe in _OFFICE_PROCESSES:
            result = self._run_ps(
                f"Get-Process -Name '{exe[:-4]}' -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue"
            )
            if "error" not in result:
                closed.append(exe)
        return {"success": True, "attempted": closed}
