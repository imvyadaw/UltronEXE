"""Cloud Sync Manager
=====================
Status and control for desktop cloud-sync clients (OneDrive, Google
Drive, Dropbox): whether each is installed/running, where OneDrive's
synced folder lives, and pausing/resuming sync.

None of these providers ship a stable, documented CLI for pause/resume
(unlike partition_manager.py/format_manager.py/raid_manager.py, which
wrap official PowerShell cmdlets). The honest mechanism available here
is process-level: pause_sync() ends the client process (sync stops
until it's running again) and resume_sync() relaunches it from its
installed location. This is a real functional equivalent - no syncing
happens while the process is down - but it is coarser than the
providers' own tray-icon "Pause syncing" menus, which pause without
fully quitting. get_onedrive_folder() is the one read that's genuinely
reliable, since OneDrive records its sync root in the registry.

Distinct from system_control/files/sync.py (ULTRON's own generic
folder-mirroring/sync utility) - this module controls third-party
cloud-provider client applications, not a ULTRON-native sync feature.

pause_sync/resume_sync are confirm-gated since ending a sync client
mid-transfer can leave files partially uploaded/downloaded until the
next successful sync. Read-only methods need no admin; process
start/stop needs no admin either (these are per-user applications).
"""

import os
import subprocess
from typing import Dict, Optional

_PROVIDERS = {
    "onedrive": {
        "process": "OneDrive.exe",
        "default_paths": [
            r"%LOCALAPPDATA%\Microsoft\OneDrive\OneDrive.exe",
        ],
    },
    "googledrive": {
        "process": "GoogleDriveFS.exe",
        "default_paths": [
            r"%PROGRAMFILES%\Google\Drive File Stream\launch.bat",
            r"%PROGRAMFILES%\Google\Drive File Stream\*\GoogleDriveFS.exe",
        ],
    },
    "dropbox": {
        "process": "Dropbox.exe",
        "default_paths": [
            r"%APPDATA%\Dropbox\bin\Dropbox.exe",
            r"%LOCALAPPDATA%\Dropbox\Dropbox.exe",
        ],
    },
}


class CloudSyncManager:
    """Detect and control desktop cloud-sync client processes."""

    def _run(self, cmd, timeout: float = 15.0) -> Dict:
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
            return {
                "success": result.returncode == 0,
                "stdout": result.stdout.strip(),
                "stderr": result.stderr.strip(),
            }
        except FileNotFoundError:
            return {"error": f"Command not found: {cmd[0]}"}
        except subprocess.TimeoutExpired:
            return {"error": "Command timed out"}
        except Exception as e:
            return {"error": str(e)}

    def _run_ps(self, script: str, timeout: float = 15.0) -> Dict:
        return self._run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script], timeout)

    def _validate_provider(self, provider: str) -> Optional[Dict]:
        if provider not in _PROVIDERS:
            return {"error": f"Unknown provider {provider!r}. Choose from: {', '.join(_PROVIDERS)}."}
        return None

    def list_providers(self) -> Dict:
        """List supported cloud-sync providers and whether each is
        currently running."""
        return {"providers": [self.get_status(p) for p in _PROVIDERS]}

    def get_status(self, provider: str) -> Dict:
        """Check whether a provider's sync client process is running."""
        err = self._validate_provider(provider)
        if err:
            return err
        info = _PROVIDERS[provider]
        result = self._run(["tasklist", "/FI", f"IMAGENAME eq {info['process']}", "/FO", "CSV", "/NH"])
        if "error" in result:
            return result
        running = info["process"].lower() in result["stdout"].lower()
        return {"provider": provider, "process": info["process"], "running": running}

    def get_onedrive_folder(self) -> Dict:
        """Read OneDrive's synced root folder path from the registry
        (personal account). No admin needed."""
        result = self._run_ps(
            "(Get-ItemProperty -Path 'HKCU:\\Software\\Microsoft\\OneDrive\\Accounts\\Personal' "
            "-Name 'UserFolder' -ErrorAction SilentlyContinue).UserFolder"
        )
        if "error" in result:
            return result
        if not result["success"] or not result["stdout"]:
            return {"error": "Could not find a OneDrive personal account sync folder - it may not be signed in."}
        return {"provider": "onedrive", "sync_folder": result["stdout"].strip()}

    def _locate_exe(self, provider: str) -> Optional[str]:
        for pattern in _PROVIDERS[provider]["default_paths"]:
            expanded = os.path.expandvars(pattern)
            if "*" in expanded:
                import glob

                matches = glob.glob(expanded)
                if matches:
                    return matches[0]
            elif os.path.exists(expanded):
                return expanded
        return None

    def pause_sync(self, provider: str, confirm: bool = False) -> Dict:
        """Stop syncing by ending the provider's client process. No
        syncing happens again until resume_sync() relaunches it.
        Confirm-gated - can leave an in-flight transfer incomplete
        until the client restarts and reconciles."""
        err = self._validate_provider(provider)
        if err:
            return err
        if not confirm:
            return {
                "requires_confirmation": True,
                "preview": (
                    f"This will quit {_PROVIDERS[provider]['process']}, stopping all syncing for {provider} "
                    "until it's relaunched. Any file mid-transfer may be left incomplete until then."
                ),
            }
        result = self._run(["taskkill", "/IM", _PROVIDERS[provider]["process"], "/F"])
        if "error" in result:
            return result
        if not result["success"]:
            return {"error": result["stderr"] or f"{provider} does not appear to be running."}
        return {"success": True, "provider": provider, "paused": True}

    def resume_sync(self, provider: str, confirm: bool = False) -> Dict:
        """Relaunch a provider's client process to resume syncing.
        Confirm-gated for symmetry with pause_sync, though relaunching
        is low-risk and reversible by pausing again."""
        err = self._validate_provider(provider)
        if err:
            return err
        exe_path = self._locate_exe(provider)
        if not exe_path:
            return {"error": f"Could not locate {provider}'s executable in its default install locations."}
        if not confirm:
            return {
                "requires_confirmation": True,
                "preview": f"This will relaunch {exe_path} to resume {provider} syncing.",
            }
        try:
            subprocess.Popen([exe_path], creationflags=getattr(subprocess, "DETACHED_PROCESS", 0))
        except Exception as e:
            return {"error": str(e)}
        return {"success": True, "provider": provider, "resumed": True, "launched": exe_path}
