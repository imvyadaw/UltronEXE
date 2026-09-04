"""Lock Screen Manager
=====================
Reads and controls the Windows lock screen's appearance and the
screensaver/auto-lock timer that brings it up - the same settings
under Settings > Personalization > Lock screen and the "On resume,
display logon screen" / screensaver timeout in Control Panel. All
HKCU, no admin needed:
  - HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\ContentDeliveryManager:
    RotatingLockScreenEnabled (1 = Windows Spotlight), RotatingLockScreenOverlayEnabled
    (1 = show the "fun facts / tips" text overlay on Spotlight images).
  - HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\PersonalizationCSP:
    LockScreenImagePath / LockScreenImageStatus (a static picture) -
    the same CSP Windows itself uses to apply a lock screen image.
  - HKCU\\Control Panel\\Desktop: ScreenSaveActive, ScreenSaveTimeOut
    (seconds), ScreenSaverIsSecure ('1' = require sign-in on resume) -
    the classic screensaver settings, which on modern Windows is what
    actually governs when the lock screen appears after inactivity
    (Settings' "Screen timeout" is the display-off timer, a separate,
    power-plan-based setting already covered by
    windows/system_info/power.py, not this module).

Distinct from windows/system_info/power.py's lock_screen() (locks the
session RIGHT NOW - a mechanical action) - this module is the lock
screen's look and its auto-lock timing, not triggering a lock.

All of these are per-user cosmetic/timing preferences, same class as
theme_manager.py's toggles, so nothing here is confirm-gated.
"""

import subprocess
from pathlib import Path
from typing import Dict, Optional


class LockScreenManager:
    """Inspect and control the Windows lock screen's background and auto-lock timing."""

    _CDM_KEY = r"HKCU\Software\Microsoft\Windows\CurrentVersion\ContentDeliveryManager"
    _PERSONALIZATION_CSP_KEY = r"HKCU\Software\Microsoft\Windows\CurrentVersion\PersonalizationCSP"
    _DESKTOP_KEY = r"HKCU\Control Panel\Desktop"

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

    def _read_value(self, key: str, name: str) -> Optional[str]:
        script = f"(Get-ItemProperty -Path \"Registry::{key}\" -Name '{name}' -ErrorAction SilentlyContinue).'{name}'"
        result = self._run_ps(script)
        if "error" in result or not result.get("success"):
            return None
        raw = result["stdout"].strip()
        return raw if raw != "" else None

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

    def _write_string(self, key: str, name: str, value: str) -> Dict:
        escaped = value.replace("'", "''")
        script = (
            f'New-Item -Path "Registry::{key}" -Force | Out-Null; '
            f"Set-ItemProperty -Path \"Registry::{key}\" -Name '{name}' -Value '{escaped}' -Type String -Force"
        )
        result = self._run_ps(script)
        if "error" in result:
            return result
        if not result["success"]:
            return {"error": result["stderr"] or f"Failed to set {name}."}
        return {"success": True}

    def get_background_mode(self) -> Dict:
        """Read the lock screen background mode: 'windows_spotlight',
        'picture', or 'unknown' if neither flag is set."""
        spotlight = self._read_value(self._CDM_KEY, "RotatingLockScreenEnabled")
        picture = self._read_value(self._PERSONALIZATION_CSP_KEY, "LockScreenImageStatus")
        if spotlight == "1":
            return {"mode": "windows_spotlight"}
        if picture == "1":
            path = self._read_value(self._PERSONALIZATION_CSP_KEY, "LockScreenImagePath")
            return {"mode": "picture", "image_path": path}
        return {"mode": "unknown"}

    def set_windows_spotlight(self, show_fun_facts: bool = True) -> Dict:
        """Switch the lock screen to Windows Spotlight (rotating curated
        images). show_fun_facts controls the tips/trivia text overlay
        Spotlight sometimes shows. Not confirm-gated."""
        r1 = self._write_dword(self._CDM_KEY, "RotatingLockScreenEnabled", 1)
        if "error" in r1:
            return r1
        r2 = self._write_dword(self._CDM_KEY, "RotatingLockScreenOverlayEnabled", 1 if show_fun_facts else 0)
        if "error" in r2:
            return r2
        self._write_dword(self._PERSONALIZATION_CSP_KEY, "LockScreenImageStatus", 0)
        return {"success": True, "mode": "windows_spotlight", "show_fun_facts": show_fun_facts}

    def set_picture(self, image_path: str) -> Dict:
        """Set a static picture as the lock screen background, turning
        off Windows Spotlight. Not confirm-gated."""
        p = Path(image_path).expanduser()
        if not p.exists():
            return {"error": f"Image not found: {image_path}"}
        r1 = self._write_dword(self._CDM_KEY, "RotatingLockScreenEnabled", 0)
        if "error" in r1:
            return r1
        r2 = self._write_string(self._PERSONALIZATION_CSP_KEY, "LockScreenImagePath", str(p))
        if "error" in r2:
            return r2
        r3 = self._write_string(self._PERSONALIZATION_CSP_KEY, "LockScreenImageUrl", str(p))
        if "error" in r3:
            return r3
        r4 = self._write_dword(self._PERSONALIZATION_CSP_KEY, "LockScreenImageStatus", 1)
        if "error" in r4:
            return r4
        return {"success": True, "mode": "picture", "image_path": str(p)}

    def get_lock_timeout(self) -> Dict:
        """Read the idle time (seconds) before the screensaver/lock screen
        engages, whether it's active at all, and whether resuming requires
        signing back in."""
        active = self._read_value(self._DESKTOP_KEY, "ScreenSaveActive")
        timeout = self._read_value(self._DESKTOP_KEY, "ScreenSaveTimeOut")
        secure = self._read_value(self._DESKTOP_KEY, "ScreenSaverIsSecure")
        return {
            "active": active == "1",
            "timeout_seconds": int(timeout) if timeout and timeout.isdigit() else None,
            "require_signin_on_resume": secure == "1",
        }

    def set_lock_timeout(self, timeout_seconds: int, require_signin_on_resume: bool = True) -> Dict:
        """Set the idle time (seconds) before Windows locks the session.
        Pass 0 to turn the timer off entirely. Not confirm-gated."""
        if timeout_seconds < 0:
            return {"error": "timeout_seconds must be 0 or greater."}
        if timeout_seconds == 0:
            r = self._write_string(self._DESKTOP_KEY, "ScreenSaveActive", "0")
            if "error" in r:
                return r
            return {"success": True, "active": False, "timeout_seconds": 0}
        r1 = self._write_string(self._DESKTOP_KEY, "ScreenSaveActive", "1")
        if "error" in r1:
            return r1
        r2 = self._write_string(self._DESKTOP_KEY, "ScreenSaveTimeOut", str(timeout_seconds))
        if "error" in r2:
            return r2
        r3 = self._write_string(self._DESKTOP_KEY, "ScreenSaverIsSecure", "1" if require_signin_on_resume else "0")
        if "error" in r3:
            return r3
        return {
            "success": True,
            "active": True,
            "timeout_seconds": timeout_seconds,
            "require_signin_on_resume": require_signin_on_resume,
        }

    def get_show_detailed_status(self) -> Dict:
        """Read whether the lock screen shows the 'fun facts, tips, and
        more' overlay text (Spotlight-only setting)."""
        overlay = self._read_value(self._CDM_KEY, "RotatingLockScreenOverlayEnabled")
        return {"show_detailed_status": overlay == "1"}

    def set_show_detailed_status(self, enabled: bool) -> Dict:
        """Turn the Spotlight 'fun facts, tips, and more' overlay text
        on/off. Only has a visible effect when the background mode is
        windows_spotlight. Not confirm-gated."""
        result = self._write_dword(self._CDM_KEY, "RotatingLockScreenOverlayEnabled", 1 if enabled else 0)
        if "error" in result:
            return result
        return {"success": True, "show_detailed_status": enabled}
