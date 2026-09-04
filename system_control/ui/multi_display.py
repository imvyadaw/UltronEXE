"""Multi-Display Manager
========================
Controls how multiple monitors work together - display mode
(extend/duplicate/second-screen-only/PC-screen-only, the same 4
options as Win+P), which monitor is primary, and relative monitor
position - the drag-to-arrange grid under Settings > System > Display.

Distinct from windows/display/monitor.py's list_monitors (geometry-only
enumeration) and display_resolution.py (per-monitor resolution/refresh
rate) - this module is specifically about how the monitors relate to
EACH OTHER, not any one monitor's own mode.

Display-mode switching is done via the built-in DisplaySwitch.exe (the
same executable Win+P calls) rather than reimplementing its
CCD/QueryDisplayConfig logic - it is the one Microsoft-supported way to
do this reliably across driver/GPU combinations. Setting the primary
display and repositioning monitors use ChangeDisplaySettingsEx
directly, following display_resolution.py's DEVMODE/CDS_TEST pattern.

set_display_mode and set_primary_display are genuinely disruptive -
mode switching can blank one or more screens for a moment (or leave a
laptop's own screen off entirely on 'second_screen_only'), and setting
a new primary display re-anchors the taskbar and every maximized
window - so both are confirm-gated. Repositioning (set_display_position)
only changes cursor/window-drag continuity between monitors, nothing
goes blank, so it is not gated, matching the cosmetic-preference
convention used elsewhere in this package.
"""

import ctypes
import subprocess
from typing import Dict, List

from system_control.ui.display_resolution import DISP_CHANGE_SUCCESSFUL, DisplayResolutionManager

DM_POSITION = 0x20
CDS_SET_PRIMARY = 0x00000008
CDS_UPDATEREGISTRY = 0x00000001
CDS_NORESET = 0x10000000

_MODE_FLAGS = {
    "extend": "/extend",
    "duplicate": "/clone",
    "second_screen_only": "/external",
    "pc_screen_only": "/internal",
}


class MultiDisplayManager:
    """Control display mode, primary monitor, and monitor arrangement."""

    def __init__(self):
        self._res = DisplayResolutionManager()

    def _run(self, args: List[str], timeout: float = 15.0) -> Dict:
        try:
            result = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
            return {"success": result.returncode == 0, "stdout": result.stdout.strip(), "stderr": result.stderr.strip()}
        except FileNotFoundError:
            return {"error": f"{args[0]} not found - this is only available on Windows."}
        except subprocess.TimeoutExpired:
            return {"error": "Command timed out"}
        except Exception as e:
            return {"error": str(e)}

    def list_displays(self) -> Dict:
        """List every attached display with its device name, resolution,
        refresh rate, and virtual-screen position - a superset of
        windows/display/monitor.py's list_monitors that includes device
        names so other methods here can target a specific one."""
        devices_result = self._res.list_devices()
        if "error" in devices_result:
            return devices_result
        displays = []
        for dev in devices_result["devices"]:
            name = dev["device_name"]
            devmode = self._res._get_devmode(name)
            if devmode is None:
                continue
            displays.append(
                {
                    "device_name": name,
                    "adapter": dev["adapter"],
                    "width": devmode.dmPelsWidth,
                    "height": devmode.dmPelsHeight,
                    "refresh_rate_hz": devmode.dmDisplayFrequency,
                    "position_x": devmode.dmPositionX,
                    "position_y": devmode.dmPositionY,
                    "is_primary": devmode.dmPositionX == 0 and devmode.dmPositionY == 0,
                }
            )
        return {"displays": displays, "count": len(displays)}

    def get_display_mode(self) -> Dict:
        """Best-effort read of the current mode: 'duplicate' if all
        attached displays share position (0,0), otherwise 'extend'.
        Windows doesn't expose a direct 'which Win+P mode is active'
        API, so single-monitor setups report as 'pc_screen_only'."""
        displays = self.list_displays()
        if "error" in displays:
            return displays
        count = displays["count"]
        if count <= 1:
            return {"mode": "pc_screen_only", "display_count": count}
        positions = {(d["position_x"], d["position_y"]) for d in displays["displays"]}
        return {"mode": "duplicate" if len(positions) == 1 else "extend", "display_count": count}

    def set_display_mode(self, mode: str, confirm: bool = False) -> Dict:
        """Switch display mode: 'extend', 'duplicate', 'second_screen_only',
        or 'pc_screen_only' (same 4 options as Win+P). Confirm-gated -
        can blank one or more screens momentarily, and 'second_screen_only'
        turns the built-in laptop screen off entirely."""
        flag = _MODE_FLAGS.get(mode.lower().strip())
        if flag is None:
            return {"error": f"mode must be one of {sorted(_MODE_FLAGS.keys())}."}
        if not confirm:
            return {
                "error": f"Switching to '{mode}' can blank one or more screens momentarily. Call again with confirm=True to proceed.",
                "requires_confirmation": True,
            }
        result = self._run(["DisplaySwitch.exe", flag])
        if "error" in result:
            return result
        if not result["success"]:
            return {"error": result["stderr"] or f"DisplaySwitch.exe {flag} failed."}
        return {"success": True, "mode": mode}

    def set_primary_display(self, device_name: str, confirm: bool = False) -> Dict:
        """Make the given device the primary display. This re-anchors
        the taskbar/Start button and every maximized window, so it is
        confirm-gated. Repositions every other monitor's coordinates
        relative to the new (0,0) origin, matching what the Settings
        UI does under the hood."""
        if not confirm:
            return {
                "error": "Changing the primary display moves the taskbar and re-anchors maximized windows. Call again with confirm=True to proceed.",
                "requires_confirmation": True,
            }
        try:
            target = self._res._get_devmode(device_name)
            if target is None:
                return {"error": f"Could not read settings for device '{device_name}'."}
            dx, dy = target.dmPositionX, target.dmPositionY
            if dx == 0 and dy == 0:
                return {"success": True, "device_name": device_name, "note": "Already the primary display."}

            devices = self._res.list_devices()
            if "error" in devices:
                return devices

            # Re-express every display's position relative to the new origin,
            # then apply the target first with CDS_SET_PRIMARY, matching the
            # documented order for SetDisplayConfig-less primary switches.
            for dev in devices["devices"]:
                name = dev["device_name"]
                devmode = self._res._get_devmode(name)
                if devmode is None:
                    continue
                devmode.dmPositionX -= dx
                devmode.dmPositionY -= dy
                devmode.dmFields = DM_POSITION
                flags = (
                    (CDS_SET_PRIMARY | CDS_UPDATEREGISTRY | CDS_NORESET)
                    if name == device_name
                    else (CDS_UPDATEREGISTRY | CDS_NORESET)
                )
                ctypes.windll.user32.ChangeDisplaySettingsExW(name, ctypes.byref(devmode), None, flags, None)

            result = ctypes.windll.user32.ChangeDisplaySettingsExW(None, None, None, 0, None)
            if result != DISP_CHANGE_SUCCESSFUL:
                return {"error": f"Failed to apply the primary-display change (code {result})."}
            return {"success": True, "primary_device": device_name}
        except Exception as e:
            return {"error": str(e)}

    def set_display_position(self, device_name: str, x: int, y: int, confirm: bool = False) -> Dict:
        """Move a monitor's position in the virtual-desktop arrangement
        (the drag-to-arrange grid in Settings > Display), so cursor/
        window-drag continuity between monitors matches their physical
        layout. Not confirm-gated - nothing goes blank, this only
        affects edge-to-edge continuity between monitors."""
        try:
            devmode = self._res._get_devmode(device_name)
            if devmode is None:
                return {"error": f"Could not read settings for device '{device_name}'."}
            devmode.dmPositionX = x
            devmode.dmPositionY = y
            devmode.dmFields = DM_POSITION
            result = ctypes.windll.user32.ChangeDisplaySettingsExW(
                device_name, ctypes.byref(devmode), None, CDS_UPDATEREGISTRY | CDS_NORESET, None
            )
            if result != DISP_CHANGE_SUCCESSFUL:
                return {"error": f"Failed to reposition '{device_name}' (code {result})."}
            ctypes.windll.user32.ChangeDisplaySettingsExW(None, None, None, 0, None)
            return {"success": True, "device_name": device_name, "position_x": x, "position_y": y}
        except Exception as e:
            return {"error": str(e)}
