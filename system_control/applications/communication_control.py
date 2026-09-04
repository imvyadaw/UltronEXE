"""Communication Control
========================
OS-level, category-wide messaging/calling app management - distinct
from apps/communication/*.py (whatsapp.py, telegram.py, discord.py,
slack.py, signal.py, skype.py, messenger.py), which each drive one
already-open app instance via UI automation to actually send a
message. This module instead operates on "communication apps" as an
installed category: which ones are on this machine, whether each is
set to auto-launch at sign-in, and bulk process actions across all of
them at once.

Startup-status reads use the same Run-key/StartupApproved convention
as system_control/process/startup_manager.py rather than duplicating
its full add/remove/enable/disable surface - that module remains the
one place to actually change a startup entry; this module only reports
which of the known communication apps currently have one, filtered to
this category.
"""
import logging

import os
import subprocess
import winreg
from typing import Dict, List

# exe name -> friendly name, for install detection, startup-status
# lookup, and bulk close.
_COMM_PROCESSES = {
    "whatsapp.exe": "WhatsApp",
    "telegram.exe": "Telegram",
    "discord.exe": "Discord",
    "slack.exe": "Slack",
    "signal.exe": "Signal",
    "skype.exe": "Skype",
    "messenger.exe": "Messenger",
    "ms-teams.exe": "Teams",
    "zoom.exe": "Zoom",
}

_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


class CommunicationControl:
    """Installed communication-app discovery, startup-launch status,
    and bulk close across all of them."""

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

    def list_installed_comm_apps(self) -> Dict:
        """List which known communication apps have a resolvable exe
        on this machine, checked via the App Paths registry first and
        common per-user install locations as a fallback (most of these
        ship as per-user installs, not machine-wide App Paths entries).
        No admin needed."""
        found: List[Dict] = []
        local_appdata = os.environ.get("LOCALAPPDATA", "")
        for exe, friendly in _COMM_PROCESSES.items():
            path = None
            try:
                with winreg.OpenKey(
                    winreg.HKEY_LOCAL_MACHINE,
                    rf"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\{exe}",
                ) as key:
                    path, _ = winreg.QueryValueEx(key, "")
            except FileNotFoundError:
                logging.getLogger(__name__).exception("Suppressed FileNotFoundError")
            if not path and local_appdata:
                guess = os.path.join(local_appdata, "Programs", friendly, exe)
                if os.path.isfile(guess):
                    path = guess
            if path and os.path.isfile(path):
                found.append({"app": friendly, "exe": exe, "path": path})
        return {"apps": found, "count": len(found)}

    def get_startup_status(self) -> Dict:
        """For each known communication app, report whether it has a
        HKCU Run-key entry (auto-launches at sign-in). Read-only view
        filtered to this category - to actually add/remove/enable/
        disable an entry, use
        system_control/process/startup_manager.py. No admin needed."""
        statuses: List[Dict] = []
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY) as key:
                entries = {}
                i = 0
                while True:
                    try:
                        name, value, _ = winreg.EnumValue(key, i)
                        entries[name.lower()] = value
                        i += 1
                    except OSError:
                        break
        except FileNotFoundError:
            entries = {}
        for exe, friendly in _COMM_PROCESSES.items():
            match = next((v for k, v in entries.items() if friendly.lower() in k or exe[:-4].lower() in k), None)
            statuses.append({"app": friendly, "auto_launch_at_startup": match is not None, "command": match})
        return {"apps": statuses}

    def close_all_comm_apps(self, confirm: bool = False) -> Dict:
        """Force-close every running process from _COMM_PROCESSES.
        Confirm-gated - closes without a save/draft prompt, and drops
        any in-progress calls."""
        if not confirm:
            return {
                "requires_confirmation": True,
                "preview": "This will force-close every running communication app (WhatsApp, Telegram, Discord, Slack, Signal, Skype, Messenger, Teams, Zoom).",
            }
        closed = []
        for exe in _COMM_PROCESSES:
            result = self._run_ps(
                f"Get-Process -Name '{exe[:-4]}' -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue"
            )
            if "error" not in result:
                closed.append(exe)
        return {"success": True, "attempted": closed}
