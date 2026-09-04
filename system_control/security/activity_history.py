"""Activity History Manager
============================
Windows' Activity History / Timeline feature - the record of apps
used and documents opened, optionally synced to a Microsoft account
so it can be resumed on another device. Backed by
HKLM\\SOFTWARE\\Policies\\Microsoft\\Windows\\System (EnableActivityFeed,
PublishUserActivities, UploadUserActivities). Distinct from
privacy_manager.py (global telemetry/advertising toggles) and
app_permissions.py (per-app sensor grants) - this is specifically the
cross-device "what have I been doing" feed, not diagnostic data or
sensor access.

get_status() is a plain read. Toggling collection/upload and clearing
history are confirm-gated - clearing especially, since it is
irreversible and (for the local cache) requires closing the shell
process that owns the file.
"""

import os
import subprocess
from pathlib import Path
from typing import Dict


class ActivityHistoryManager:
    """Inspect and control Windows Activity History (Timeline) collection."""

    _KEY = r"HKLM\SOFTWARE\Policies\Microsoft\Windows\System"
    _CACHE_DB = Path(os.environ.get("LOCALAPPDATA", "")) / "ConnectedDevicesPlatform"

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

    def get_status(self) -> Dict:
        """Read whether activity collection, local publishing, and
        cross-device upload are each enabled."""
        script = (
            f"$k = '{self._KEY}'; "
            "[PSCustomObject]@{"
            'EnableActivityFeed = (Get-ItemProperty -Path "Registry::$k" -Name EnableActivityFeed -ErrorAction SilentlyContinue).EnableActivityFeed; '
            'PublishUserActivities = (Get-ItemProperty -Path "Registry::$k" -Name PublishUserActivities -ErrorAction SilentlyContinue).PublishUserActivities; '
            'UploadUserActivities = (Get-ItemProperty -Path "Registry::$k" -Name UploadUserActivities -ErrorAction SilentlyContinue).UploadUserActivities '
            "} | ConvertTo-Json"
        )
        result = self._run_ps(script)
        if "error" in result:
            return result
        if not result["success"]:
            return {"error": self._admin_hint(result["stderr"] or "Could not read Activity History status.")}
        import json

        try:
            data = json.loads(result["stdout"]) if result["stdout"] else {}
        except Exception:
            return {"error": "Could not parse Activity History status.", "raw": result["stdout"]}

        def _bool(v):
            return bool(v) if v is not None else None

        return {
            "collection_enabled": _bool(data.get("EnableActivityFeed")),
            "local_publish_enabled": _bool(data.get("PublishUserActivities")),
            "cloud_upload_enabled": _bool(data.get("UploadUserActivities")),
            "note": "Any value showing as null/None means it's unset and Windows is using its default (on).",
        }

    def set_collection_enabled(self, enabled: bool, confirm: bool = False) -> Dict:
        """Turn Activity History collection on/off machine-wide (this also
        gates local publishing and cloud upload downstream). Confirm-gated,
        needs admin."""
        if not confirm:
            return {
                "requires_confirmation": True,
                "preview": f"This will {'ENABLE' if enabled else 'DISABLE'} Windows Activity History "
                f"collection machine-wide (app/document usage tracking for Timeline).",
            }
        script = (
            f"$p = 'Registry::{self._KEY}'; "
            f"if (-not (Test-Path $p)) {{ New-Item -Path $p -Force | Out-Null }}; "
            f"Set-ItemProperty -Path $p -Name EnableActivityFeed -Value {1 if enabled else 0} -Type DWord"
        )
        result = self._run_ps(script)
        if "error" in result:
            return result
        if not result["success"]:
            return {"error": self._admin_hint(result["stderr"] or "Failed to set Activity History collection.")}
        return {"success": True, "collection_enabled": enabled}

    def set_cloud_upload_enabled(self, enabled: bool, confirm: bool = False) -> Dict:
        """Turn cross-device cloud sync of activity history on/off,
        independent of local collection. Confirm-gated, needs admin -
        this decides whether your activity leaves this machine at all."""
        if not confirm:
            return {
                "requires_confirmation": True,
                "preview": f"This will {'ENABLE' if enabled else 'DISABLE'} uploading activity history "
                f"to your Microsoft account for cross-device Timeline.",
            }
        script = (
            f"$p = 'Registry::{self._KEY}'; "
            f"if (-not (Test-Path $p)) {{ New-Item -Path $p -Force | Out-Null }}; "
            f"Set-ItemProperty -Path $p -Name UploadUserActivities -Value {1 if enabled else 0} -Type DWord; "
            f"Set-ItemProperty -Path $p -Name PublishUserActivities -Value {1 if enabled else 0} -Type DWord"
        )
        result = self._run_ps(script)
        if "error" in result:
            return result
        if not result["success"]:
            return {"error": self._admin_hint(result["stderr"] or "Failed to set cloud upload setting.")}
        return {"success": True, "cloud_upload_enabled": enabled}

    def clear_local_history(self, confirm: bool = False) -> Dict:
        """Clear the local Activity History cache (ConnectedDevicesPlatform
        database). Irreversible, and best-effort: the file is locked while
        Explorer/the shell experience host owns it, so this may report a
        sharing violation - if so, the built-in Settings > Privacy >
        Activity history > 'Clear' button is the reliable fallback.
        Confirm-gated."""
        if not confirm:
            return {
                "requires_confirmation": True,
                "preview": "This will permanently delete the local Activity History cache. Cannot be undone.",
            }
        if not self._CACHE_DB.exists():
            return {"error": f"Activity History cache folder not found at {self._CACHE_DB}."}
        script = (
            "Stop-Process -Name ShellExperienceHost -Force -ErrorAction SilentlyContinue; "
            f"Get-ChildItem -Path '{self._CACHE_DB}' -Recurse -Filter 'ActivitiesCache.db*' -ErrorAction SilentlyContinue | "
            "Remove-Item -Force -ErrorAction Stop"
        )
        result = self._run_ps(script)
        if "error" in result:
            return result
        if not result["success"]:
            return {
                "error": self._admin_hint(
                    result["stderr"]
                    or "Could not delete the cache - it's likely locked. Use Settings > Privacy & security "
                    "> Activity history > Clear as a fallback."
                )
            }
        return {"success": True, "note": "Local activity history cache cleared."}
