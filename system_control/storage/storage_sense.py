"""Storage Sense
================
Reads and configures Windows Storage Sense - the automatic disk
cleanup feature (Settings > System > Storage > Storage Sense) that
periodically deletes temp files, empties the Recycle Bin, cleans up
Downloads, and frees space from cloud-only files. Controlled entirely
through per-user registry values under HKCU:\\Software\\Microsoft\\
Windows\\CurrentVersion\\StorageSense\\Parameters\\StoragePolicy -
there is no first-class PowerShell cmdlet for it (unlike
partition_manager.py/format_manager.py, which wrap officially
documented Storage module cmdlets). These registry value names
(01, 02, 04, 08, 32, 128, 512) are undocumented by Microsoft but
stable across Windows 10/11 and are the same values the Settings UI
itself writes - still, treat get_status() as the source of truth
after any change rather than assuming a write always sticks.
run_now() instead triggers the actual "Storage Sense" scheduled task
so cleanup runs immediately rather than waiting for its schedule.

Distinct from system_control/files/ (manual file operations) and
system_control/storage/format_manager.py (volume-level formatting) -
this module is about the OS's *automatic, policy-driven* cleanup
behavior, not one-off file or volume actions.

All settings here are HKCU (per-user) and reversible - no method is
confirm-gated. Nothing here needs admin.
"""

import subprocess
from typing import Dict, Optional

_POLICY_PATH = r"HKCU:\Software\Microsoft\Windows\CurrentVersion\StorageSense\Parameters\StoragePolicy"

# Registry value name -> meaning, per the undocumented-but-stable Storage Sense schema.
_VALUES = {
    "enabled": "01",  # 0/1 - master on/off switch
    "run_frequency_days": "02",  # 0=low disk space, 1=daily, 7=weekly, 30=monthly
    "temp_files_enabled": "04",  # 0/1 - clean temp files Storage Sense creates
    "recycle_bin_days": "08",  # 0=never, else days before auto-empty
    "downloads_days": "32",  # 0=never, else days before Downloads cleanup
    "cloud_content_days": "128",  # 0=never, else days before making cloud files online-only
}


class StorageSense:
    """Read and configure Windows Storage Sense's automatic cleanup policy."""

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

    def _get_value(self, reg_name: str) -> Optional[int]:
        result = self._run_ps(
            f"(Get-ItemProperty -Path '{_POLICY_PATH}' -Name '{reg_name}' -ErrorAction SilentlyContinue).'{reg_name}'"
        )
        if "error" in result or not result["success"] or not result["stdout"]:
            return None
        try:
            return int(result["stdout"].strip())
        except ValueError:
            return None

    def _set_value(self, reg_name: str, value: int) -> Dict:
        result = self._run_ps(
            f"New-Item -Path '{_POLICY_PATH}' -Force | Out-Null; "
            f"New-ItemProperty -Path '{_POLICY_PATH}' -Name '{reg_name}' -Value {value} "
            f"-PropertyType DWord -Force | Out-Null"
        )
        if "error" in result:
            return result
        if not result["success"]:
            return {"error": result["stderr"] or f"Failed to set {reg_name}."}
        return {"success": True}

    def get_status(self) -> Dict:
        """Read every Storage Sense policy value at once. Any value that's
        never been set (Storage Sense untouched since install) reads as
        None, which behaves the same as Windows' own default (off)."""
        return {label: self._get_value(reg_name) for label, reg_name in _VALUES.items()}

    def set_enabled(self, enabled: bool = True) -> Dict:
        """Turn Storage Sense on or off entirely."""
        result = self._set_value(_VALUES["enabled"], 1 if enabled else 0)
        if "error" in result:
            return result
        return {"success": True, "enabled": enabled}

    def set_run_frequency(self, days: int) -> Dict:
        """Set how often Storage Sense runs automatically: 0 = only when
        low on disk space, 1 = daily, 7 = weekly, 30 = monthly."""
        if days not in (0, 1, 7, 30):
            return {"error": "days must be one of 0 (low disk space), 1, 7, or 30."}
        result = self._set_value(_VALUES["run_frequency_days"], days)
        if "error" in result:
            return result
        return {"success": True, "run_frequency_days": days}

    def configure_temp_files(self, enabled: bool) -> Dict:
        """Toggle cleanup of temporary files Storage Sense itself creates
        (not general Temp folder contents)."""
        result = self._set_value(_VALUES["temp_files_enabled"], 1 if enabled else 0)
        if "error" in result:
            return result
        return {"success": True, "temp_files_enabled": enabled}

    def configure_recycle_bin(self, days: int) -> Dict:
        """Set days before Recycle Bin items older than this are
        auto-deleted. 0 disables this rule entirely."""
        if days not in (0, 1, 14, 30, 60):
            return {"error": "days must be one of 0 (never), 1, 14, 30, or 60."}
        result = self._set_value(_VALUES["recycle_bin_days"], days)
        if "error" in result:
            return result
        return {"success": True, "recycle_bin_days": days}

    def configure_downloads_cleanup(self, days: int) -> Dict:
        """Set days before untouched files in Downloads are auto-deleted.
        0 disables this rule entirely."""
        if days not in (0, 1, 14, 30, 60):
            return {"error": "days must be one of 0 (never), 1, 14, 30, or 60."}
        result = self._set_value(_VALUES["downloads_days"], days)
        if "error" in result:
            return result
        return {"success": True, "downloads_days": days}

    def configure_cloud_content(self, days: int) -> Dict:
        """Set days of inactivity before locally-available cloud files
        (e.g. OneDrive) are made online-only to free space. 0 disables
        this rule entirely."""
        if days not in (0, 1, 14, 30, 60):
            return {"error": "days must be one of 0 (never), 1, 14, 30, or 60."}
        result = self._set_value(_VALUES["cloud_content_days"], days)
        if "error" in result:
            return result
        return {"success": True, "cloud_content_days": days}

    def run_now(self) -> Dict:
        """Trigger the 'Storage Sense' scheduled task to run cleanup
        immediately instead of waiting for its schedule."""
        result = self._run_ps(
            'Start-ScheduledTask -TaskPath "\\Microsoft\\Windows\\StorageSense\\" -TaskName "Storage Sense"'
        )
        if "error" in result:
            return result
        if not result["success"]:
            return {"error": result["stderr"] or "Could not start the Storage Sense scheduled task."}
        return {"success": True, "triggered": True}
