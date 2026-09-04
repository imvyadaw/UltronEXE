"""Notification Manager
======================
Reads and controls Windows notification SETTINGS - the master toggle,
lock-screen visibility, per-app enable/sound/banner, and Focus Assist
(quiet hours) mode - the same settings under Settings > System >
Notifications. All HKCU:
  - HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\PushNotifications:
    ToastEnabled (DWORD, master on/off), LockScreenToastEnabled
    (DWORD, show on lock screen) - no admin needed.
  - HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Notifications\\Settings\\<AppId>:
    Enabled / SoundEnabled / ShowInActionCenter (DWORD, per app,
    keyed by the app's AUMID/app-id) - no admin needed.
  - HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\CloudStore\\Store\\Cache\\
    DefaultAccount\\Current\\...quiethourssettings...\\Current: Focus
    Assist's actual mode. This is an undocumented binary blob (there is
    no supported registry API or PowerShell cmdlet for Focus Assist) -
    get/set here patch the one well-known state byte community
    automation scripts have reverse-engineered for it. Best-effort:
    may not work on every Windows build, and Windows can silently
    rewrite this value on its own (e.g. when an alarm fires).

Distinct from windows/notifications/toasts.py (SENDS a toast right
now) - this module controls whether/how notifications are allowed to
appear at all, not sending one.

Master toggle, lock-screen visibility, and per-app settings are
per-user preferences and are NOT confirm-gated, same class as any
other notification-preference toggle. set_focus_assist_mode touches
an undocumented value with no official rollback path if Windows'
internal format ever changes, so it IS confirm-gated.
"""

import subprocess
from typing import Dict, Optional

_FOCUS_ASSIST_MODES = {"off": 0, "priority_only": 1, "alarms_only": 2}


class NotificationManager:
    """Inspect and control Windows notification settings and Focus Assist."""

    _PUSH_KEY = r"HKCU\Software\Microsoft\Windows\CurrentVersion\PushNotifications"
    _APP_SETTINGS_KEY = r"HKCU\Software\Microsoft\Windows\CurrentVersion\Notifications\Settings"
    _QUIET_HOURS_KEY = (
        r"HKCU\Software\Microsoft\Windows\CurrentVersion\CloudStore\Store\Cache\DefaultAccount\Current"
        "\\"
        r"Default$windows.data.notifications.quiethourssettings\Current"
    )

    def _run_ps(self, script: str, timeout: float = 15.0) -> Dict:
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

    def _read_dword(self, key: str, name: str) -> Optional[int]:
        script = f"(Get-ItemProperty -Path \"Registry::{key}\" -Name '{name}' -ErrorAction SilentlyContinue).'{name}'"
        result = self._run_ps(script)
        if "error" in result or not result.get("success"):
            return None
        raw = result["stdout"].strip()
        try:
            return int(raw)
        except (ValueError, TypeError):
            return None

    def _write_dword(self, key: str, name: str, value: int) -> Dict:
        script = (
            f'New-Item -Path "Registry::{key}" -Force | Out-Null; '
            f"Set-ItemProperty -Path \"Registry::{key}\" -Name '{name}' -Value {value} -Type DWord -Force"
        )
        result = self._run_ps(script)
        if "error" in result:
            return result
        if not result["success"]:
            return {"error": result["stderr"] or f"Failed to set {name}."}
        return {"success": True}

    def get_notifications_enabled(self) -> Dict:
        """Read the master notifications toggle and lock-screen visibility."""
        toast = self._read_dword(self._PUSH_KEY, "ToastEnabled")
        lock = self._read_dword(self._PUSH_KEY, "LockScreenToastEnabled")
        return {
            "notifications_enabled": bool(toast) if toast is not None else True,
            "show_on_lock_screen": bool(lock) if lock is not None else True,
        }

    def set_notifications_enabled(self, enabled: bool) -> Dict:
        """Turn ALL notifications on/off (the master switch at the top of
        Settings > Notifications). Not confirm-gated."""
        result = self._write_dword(self._PUSH_KEY, "ToastEnabled", 1 if enabled else 0)
        if "error" in result:
            return result
        return {"success": True, "notifications_enabled": enabled}

    def set_show_on_lock_screen(self, enabled: bool) -> Dict:
        """Turn 'notifications on the lock screen' on/off. Not confirm-gated."""
        result = self._write_dword(self._PUSH_KEY, "LockScreenToastEnabled", 1 if enabled else 0)
        if "error" in result:
            return result
        return {"success": True, "show_on_lock_screen": enabled}

    def list_app_ids(self) -> Dict:
        """List app ids (AUMIDs) that have a per-app notification entry
        - these are the entries shown under Settings > Notifications'
        per-app list."""
        script = f'(Get-ChildItem -Path "Registry::{self._APP_SETTINGS_KEY}" -ErrorAction SilentlyContinue).PSChildName'
        result = self._run_ps(script)
        if "error" in result:
            return result
        if not result["success"]:
            return {"error": result["stderr"] or "Could not list per-app notification settings."}
        app_ids = [a for a in result["stdout"].splitlines() if a.strip()]
        return {"app_ids": app_ids, "count": len(app_ids)}

    def get_app_settings(self, app_id: str) -> Dict:
        """Read one app's notification settings: enabled, sound, and
        whether it shows in Action Center."""
        key = f"{self._APP_SETTINGS_KEY}\\{app_id}"
        enabled = self._read_dword(key, "Enabled")
        sound = self._read_dword(key, "SoundEnabled")
        in_center = self._read_dword(key, "ShowInActionCenter")
        return {
            "app_id": app_id,
            "enabled": bool(enabled) if enabled is not None else True,
            "sound_enabled": bool(sound) if sound is not None else True,
            "show_in_action_center": bool(in_center) if in_center is not None else True,
        }

    def set_app_enabled(self, app_id: str, enabled: bool) -> Dict:
        """Turn one app's notifications on/off entirely. Not confirm-gated."""
        key = f"{self._APP_SETTINGS_KEY}\\{app_id}"
        result = self._write_dword(key, "Enabled", 1 if enabled else 0)
        if "error" in result:
            return result
        return {"success": True, "app_id": app_id, "enabled": enabled}

    def set_app_sound_enabled(self, app_id: str, enabled: bool) -> Dict:
        """Turn one app's notification sound on/off (banners still show
        silently if disabled). Not confirm-gated."""
        key = f"{self._APP_SETTINGS_KEY}\\{app_id}"
        result = self._write_dword(key, "SoundEnabled", 1 if enabled else 0)
        if "error" in result:
            return result
        return {"success": True, "app_id": app_id, "sound_enabled": enabled}

    def set_app_show_in_action_center(self, app_id: str, enabled: bool) -> Dict:
        """Turn whether one app's notifications persist in Action Center
        on/off. Not confirm-gated."""
        key = f"{self._APP_SETTINGS_KEY}\\{app_id}"
        result = self._write_dword(key, "ShowInActionCenter", 1 if enabled else 0)
        if "error" in result:
            return result
        return {"success": True, "app_id": app_id, "show_in_action_center": enabled}

    def get_focus_assist_mode(self) -> Dict:
        """Best-effort read of Focus Assist's current mode ('off',
        'priority_only', 'alarms_only', or 'unknown' if the value
        couldn't be parsed). Reads the first byte of the undocumented
        quiet-hours binary blob - see module docstring."""
        script = (
            f'$v = (Get-ItemProperty -Path "Registry::{self._QUIET_HOURS_KEY}" -Name Data '
            f"-ErrorAction SilentlyContinue).Data; if ($v) {{ [int]$v[0] }}"
        )
        result = self._run_ps(script)
        if "error" in result:
            return result
        if not result["success"] or not result["stdout"].strip():
            return {"mode": "unknown", "note": "Focus Assist state not found or not yet initialized by Windows."}
        try:
            byte0 = int(result["stdout"].strip())
        except ValueError:
            return {"mode": "unknown"}
        for name, val in _FOCUS_ASSIST_MODES.items():
            if val == byte0:
                return {"mode": name}
        return {"mode": "unknown", "raw_byte": byte0}

    def set_focus_assist_mode(self, mode: str, confirm: bool = False) -> Dict:
        """Best-effort set of Focus Assist mode: 'off', 'priority_only',
        or 'alarms_only'. Confirm-gated - patches an undocumented binary
        value with no official rollback if Windows' internal format
        changes; Windows may also silently overwrite it later (e.g. an
        alarm firing turns Focus Assist off automatically)."""
        if mode not in _FOCUS_ASSIST_MODES:
            return {"error": f"mode must be one of {list(_FOCUS_ASSIST_MODES)}"}
        if not confirm:
            return {
                "requires_confirmation": True,
                "preview": (
                    f"This will best-effort set Focus Assist to '{mode}' by patching an undocumented "
                    "Windows registry value - it may not take effect on every build."
                ),
            }
        byte0 = _FOCUS_ASSIST_MODES[mode]
        script = (
            f'$k = "Registry::{self._QUIET_HOURS_KEY}"; '
            f"$v = (Get-ItemProperty -Path $k -Name Data -ErrorAction SilentlyContinue).Data; "
            f"if (-not $v) {{ Write-Output 'NODATA'; exit 1 }}; "
            f"$v[0] = {byte0}; "
            f"Set-ItemProperty -Path $k -Name Data -Value $v -Type Binary -Force"
        )
        result = self._run_ps(script)
        if "error" in result:
            return result
        if not result["success"] or "NODATA" in result["stdout"]:
            return {
                "error": "Could not locate Focus Assist's stored state - it may not be initialized yet on this machine."
            }
        return {"success": True, "mode": mode}
