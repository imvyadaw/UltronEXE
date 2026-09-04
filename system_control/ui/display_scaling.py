"""Display Scaling Manager
==========================
Reads and controls two independent "make things bigger" settings under
Settings > System > Display:
  - Scale (the DPI/display-scaling percentage, e.g. 100%/125%/150%) -
    read live via GetDpiForSystem (Windows 10 1607+). Setting it isn't
    exposed through any documented per-process API - Windows only
    applies a changed system DPI at the next sign-in - so set_scaling
    writes the per-monitor registry value Windows itself reads on
    login and is explicit in its return value that a sign-out is
    required, rather than pretending it applied live.
  - Text size (the Windows 11 accessibility slider, 100-225%, under
    Settings > Accessibility > Text size) - HKCU\\Software\\Microsoft\\
    Accessibility: TextScaleFactor. This one DOES apply live, no
    sign-out needed, and is the more reliable lever for "make text
    bigger" requests.

Distinct from display_resolution.py (pixel resolution, an independent
setting from scaling - a 4K monitor might run at 150% scale while a
1080p one runs at 100%) and font_manager.py (installing/removing
fonts and ClearType, not size).

Reading is never gated. set_text_scale is a live, easily-reversible
accessibility preference - not confirm-gated. set_scaling requires a
sign-out and, on a HiDPI/mixed-DPI setup, a wrong value can make
things hard to read until the next login - confirm-gated.
"""
import logging

import ctypes
import subprocess
from typing import Dict, Optional


class DisplayScalingManager:
    """Inspect and control DPI/display scaling and accessibility text size."""

    _ACCESSIBILITY_KEY = r"HKCU\Software\Microsoft\Accessibility"
    _PER_MONITOR_KEY = r"HKCU\Control Panel\Desktop\PerMonitorSettings"

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

    # -- DPI / display scaling percentage --------------------------------
    def get_scaling(self) -> Dict:
        """Read the current system DPI scaling percentage (100% = 96 DPI)."""
        try:
            dpi = ctypes.windll.user32.GetDpiForSystem()
        except AttributeError:
            return {"error": "GetDpiForSystem needs Windows 10 1607 or later."}
        except Exception as e:
            return {"error": str(e)}
        percent = round(dpi / 96 * 100)
        return {"dpi": dpi, "scaling_percent": percent}

    def set_scaling(self, percent: int, device_id: Optional[str] = None, confirm: bool = False) -> Dict:
        """Request a new DPI scaling percentage (e.g. 100/125/150/175/200).
        Windows only picks up a changed system DPI at the next sign-in,
        so this writes the setting and tells you a sign-out is needed -
        it does not (and cannot, via any documented API) apply live.
        device_id lets you target one monitor's PerMonitorSettings
        sub-key on a mixed-DPI multi-monitor setup; omit it to change
        the DPI Windows falls back to generally. Confirm-gated - a bad
        value leaves things hard to read until the next login."""
        if not confirm:
            return {
                "error": "Changing display scaling needs a sign-out to take effect and can make things hard to read until then. Call again with confirm=True to proceed.",
                "requires_confirmation": True,
            }
        if percent not in (100, 125, 150, 175, 200, 225, 250, 300, 350, 400):
            return {
                "error": "percent should be one of the standard Windows scaling steps: 100, 125, 150, 175, 200, 225, 250, 300, 350, 400."
            }

        # LogPixels DWORD Windows reads at logon for the "general" DPI.
        log_pixels = round(96 * percent / 100)
        script = (
            r"New-Item -Path 'Registry::HKCU\Control Panel\Desktop' -Force | Out-Null; "
            f"Set-ItemProperty -Path 'Registry::HKCU\\Control Panel\\Desktop' -Name LogPixels -Value {log_pixels} -Type DWord -Force; "
            r"Set-ItemProperty -Path 'Registry::HKCU\Control Panel\Desktop' -Name Win8DpiScaling -Value 1 -Type DWord -Force"
        )
        result = self._run_ps(script)
        if "error" in result:
            return result
        if not result["success"]:
            return {"error": result["stderr"] or "Failed to write the scaling setting."}

        if device_id:
            key = f"{self._PER_MONITOR_KEY}\\{device_id}"
            per_monitor_script = (
                f'New-Item -Path "Registry::{key}" -Force | Out-Null; '
                f'Set-ItemProperty -Path "Registry::{key}" -Name DpiValue -Value {log_pixels} -Type DWord -Force'
            )
            self._run_ps(per_monitor_script)  # best-effort per-monitor override

        return {
            "success": True,
            "requested_scaling_percent": percent,
            "note": "Sign out and back in for the new scaling to take effect.",
        }

    # -- Accessibility text size (applies live, no sign-out) -----------------
    def get_text_scale(self) -> Dict:
        """Read the Windows 11 'Text size' accessibility slider value
        (100-225, in 25-point steps)."""
        script = f'(Get-ItemProperty -Path "Registry::{self._ACCESSIBILITY_KEY}" -Name TextScaleFactor -ErrorAction SilentlyContinue).TextScaleFactor'
        result = self._run_ps(script)
        if "error" in result or not result.get("success") or not result.get("stdout", "").strip():
            return {"text_scale_percent": 100}  # Windows default when the key has never been touched
        try:
            return {"text_scale_percent": int(result["stdout"].strip())}
        except ValueError:
            return {"text_scale_percent": 100}

    def set_text_scale(self, percent: int, confirm: bool = False) -> Dict:
        """Set the accessibility 'Text size' slider (100-225). Applies
        live across the shell and most apps, no sign-out needed - this
        is the right tool for a plain 'make the text bigger' request,
        as opposed to set_scaling which changes everything (icons,
        spacing, UI chrome) and needs a sign-out. Not confirm-gated."""
        percent = max(100, min(225, int(percent)))
        script = (
            f'New-Item -Path "Registry::{self._ACCESSIBILITY_KEY}" -Force | Out-Null; '
            f'Set-ItemProperty -Path "Registry::{self._ACCESSIBILITY_KEY}" -Name TextScaleFactor -Value {percent} -Type DWord -Force'
        )
        result = self._run_ps(script)
        if "error" in result:
            return result
        if not result["success"]:
            return {"error": result["stderr"] or "Failed to set text scale."}
        try:
            # Broadcast WM_SETTINGCHANGE("ImmersiveColorSet") - the same
            # notification Settings itself sends so the shell repaints live.
            HWND_BROADCAST, WM_SETTINGCHANGE = 0xFFFF, 0x001A
            ctypes.windll.user32.SendMessageTimeoutW(
                HWND_BROADCAST, WM_SETTINGCHANGE, 0, ctypes.c_wchar_p("ImmersiveColorSet"), 0, 1000, None
            )
        except Exception:
            logging.getLogger(__name__).exception("Suppressed Exception")
        return {"success": True, "text_scale_percent": percent}
