"""Mouse Control
===============
Physical-mouse device and input-behavior management - distinct from
every other mouse-adjacent module already in the codebase:

- automation/mouse/mouse.py - moves/clicks the cursor *programmatically*
  for automation. This module never moves the cursor; it manages the
  device and OS-level input settings real mouse hardware feeds into.
- system_control/ui/cursor_manager.py - already owns pointer speed
  (MouseSensitivity), the 'Enhance pointer precision' toggle
  (MouseSpeed), pointer trails, snap-to-default-button, cursor scheme/
  size/color. This module does not duplicate any of that; it covers
  what's left: primary-button swap (left/right-handed use), double-
  click speed, wheel scroll-line count, and the physical device
  itself.

Button swap, double-click speed, and wheel scroll lines are per-user
HKCU settings/Win32 SystemParametersInfo calls, same convenience class
as cursor_manager.py's own settings - not confirm-gated. Enabling/
disabling the physical mouse device is confirm-gated and needs admin,
same reasoning as keyboard_control.py's device toggle.
"""

import ctypes
import subprocess
import winreg
from typing import Dict

_SPI_GETWHEELSCROLLLINES = 0x0068
_SPI_SETWHEELSCROLLLINES = 0x0069
_SPIF_SENDCHANGE = 0x02
_SM_SWAPBUTTON = 23

_MOUSE_REG_PATH = r"Control Panel\Mouse"


class MouseHardwareControl:
    """Physical mouse device enable/disable, button swap, double-click
    speed, and wheel scroll lines - distinct from simulated clicks/
    movement and from pointer appearance/speed, both owned elsewhere."""

    def _run_ps(self, cmd: str, timeout: float = 20.0) -> Dict:
        try:
            result = subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", cmd],
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            return {"success": result.returncode == 0, "stdout": result.stdout.strip(), "stderr": result.stderr.strip()}
        except FileNotFoundError:
            return {"error": "PowerShell not found - this is only available on Windows"}
        except subprocess.TimeoutExpired:
            return {"error": "Command timed out"}
        except Exception as e:
            return {"error": str(e)}

    def _admin_hint(self, err: str) -> str:
        if err and ("denied" in err.lower() or "elevat" in err.lower()):
            return err + " - run ULTRON as Administrator."
        return err

    def list_mice(self) -> Dict:
        """All currently-known mouse/pointing devices: friendly name,
        InstanceId, and status. Use InstanceId with
        set_mouse_enabled() below. No admin needed."""
        result = self._run_ps(
            "Get-PnpDevice -Class Mouse -ErrorAction SilentlyContinue | "
            "Select-Object FriendlyName, InstanceId, Status | ConvertTo-Json"
        )
        if "error" in result:
            return result
        if not result["success"]:
            return {"error": result["stderr"] or "Get-PnpDevice failed"}
        if not result["stdout"]:
            return {"success": True, "mice": [], "count": 0}
        import json

        try:
            data = json.loads(result["stdout"])
        except json.JSONDecodeError:
            return {"error": "Could not parse mouse list"}
        mice = data if isinstance(data, list) else [data]
        return {"success": True, "mice": mice, "count": len(mice)}

    def set_mouse_enabled(self, instance_id: str, enabled: bool, confirm: bool = False) -> Dict:
        """Enable or disable a mouse device by InstanceId (from
        list_mice). Confirm-gated - if this is the only pointing
        device, disabling it can make the machine awkward to control
        until re-enabled (keyboard navigation still works). Needs
        admin."""
        if not instance_id:
            return {"error": "instance_id must be non-empty"}
        action = "enable" if enabled else "disable"
        if not confirm:
            return {
                "requires_confirmation": True,
                "preview": f"This will {action} mouse device {instance_id}. "
                f"If this is the only pointing device, disabling it leaves only keyboard navigation.",
            }
        safe_id = instance_id.replace("'", "''")
        verb = "Enable-PnpDevice" if enabled else "Disable-PnpDevice"
        result = self._run_ps(f"{verb} -InstanceId '{safe_id}' -Confirm:$false")
        if "error" in result:
            return result
        if not result["success"]:
            return {"error": self._admin_hint(result["stderr"] or f"Could not {action} mouse")}
        return {"success": True, "instance_id": instance_id, "enabled": enabled}

    def get_button_swap(self) -> Dict:
        """Whether the primary/secondary mouse buttons are currently
        swapped (left-handed mode). No admin needed."""
        try:
            return {"success": True, "swapped": bool(ctypes.windll.user32.GetSystemMetrics(_SM_SWAPBUTTON))}
        except Exception as e:
            return {"error": str(e)}

    def set_button_swap(self, swapped: bool) -> Dict:
        """Swap the primary/secondary mouse buttons (for left-handed
        use) or restore the default. Not confirm-gated - instantly
        reversible, and Windows itself treats this as an ordinary
        Settings toggle rather than something to double-check."""
        try:
            ctypes.windll.user32.SwapMouseButton(1 if swapped else 0)
            with winreg.CreateKey(winreg.HKEY_CURRENT_USER, _MOUSE_REG_PATH) as key:
                winreg.SetValueEx(key, "SwapMouseButtons", 0, winreg.REG_SZ, "1" if swapped else "0")
            return {"success": True, "swapped": swapped}
        except Exception as e:
            return {"error": str(e)}

    def get_double_click_speed(self) -> Dict:
        """Current double-click speed in milliseconds (the maximum
        gap between two clicks still counted as a double-click). No
        admin needed."""
        try:
            ms = ctypes.windll.user32.GetDoubleClickTime()
            return {"success": True, "milliseconds": int(ms)}
        except Exception as e:
            return {"error": str(e)}

    def set_double_click_speed(self, milliseconds: int) -> Dict:
        """Set double-click speed in milliseconds (Windows clamps to
        roughly 100-900ms in the Settings UI; values outside that are
        still accepted by the API but may feel unusable). Not
        confirm-gated."""
        try:
            milliseconds = max(0, int(milliseconds))
            ctypes.windll.user32.SetDoubleClickTime(milliseconds)
            return {"success": True, "milliseconds": milliseconds}
        except Exception as e:
            return {"error": str(e)}

    def get_wheel_scroll_lines(self) -> Dict:
        """Number of lines scrolled per mouse-wheel notch (Settings >
        Devices > Mouse > 'Choose how many lines to scroll'), or 'one
        screen at a time' represented as a very large sentinel value
        by Windows itself. No admin needed."""
        try:
            lines = ctypes.c_uint()
            ctypes.windll.user32.SystemParametersInfoW(_SPI_GETWHEELSCROLLLINES, 0, ctypes.byref(lines), 0)
            return {"success": True, "lines": lines.value}
        except Exception as e:
            return {"error": str(e)}

    def set_wheel_scroll_lines(self, lines: int) -> Dict:
        """Set number of lines scrolled per wheel notch. Not confirm-
        gated - a per-user convenience setting."""
        try:
            lines = max(0, int(lines))
            ctypes.windll.user32.SystemParametersInfoW(_SPI_SETWHEELSCROLLLINES, lines, None, _SPIF_SENDCHANGE)
            with winreg.CreateKey(winreg.HKEY_CURRENT_USER, r"Control Panel\Desktop") as key:
                winreg.SetValueEx(key, "WheelScrollLines", 0, winreg.REG_SZ, str(lines))
            return {"success": True, "lines": lines}
        except Exception as e:
            return {"error": str(e)}
