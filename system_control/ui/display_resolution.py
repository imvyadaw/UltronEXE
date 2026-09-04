"""Display Resolution Manager
=============================
Per-MONITOR resolution and refresh-rate control via
EnumDisplayDevices/EnumDisplaySettingsEx - the same settings under
Settings > System > Display > Advanced display.

Distinct from windows/display/monitor.py's DisplayMonitor, which only
ever targets the PRIMARY display (get_resolution/set_resolution take
no device argument) and uses EnumDisplayMonitors (HMONITOR-based,
geometry only, no device names or mode lists). This module works by
Windows device name (e.g. '\\\\.\\DISPLAY1'), so it can target any
connected monitor individually and list every resolution/refresh-rate
combination that monitor actually supports. Also distinct from
display_scaling.py (DPI/text scaling - a monitor's resolution and its
scaling percentage are independent settings) and multi_display.py
(display MODE - extend/duplicate/primary switch - not resolution).

Resolution changes are tested with CDS_TEST before being applied (same
safety check windows/display/monitor.py uses), so an unsupported mode
is rejected up front rather than leaving a blank screen. Not
confirm-gated, matching that module's precedent - a rejected-if-
unsupported resolution change is treated as a cosmetic display
preference, not a disruptive action.
"""

import ctypes
from ctypes import wintypes
from typing import Dict, List, Optional


class _DEVMODE(ctypes.Structure):
    _fields_ = [
        ("dmDeviceName", ctypes.c_wchar * 32),
        ("dmSpecVersion", ctypes.c_ushort),
        ("dmDriverVersion", ctypes.c_ushort),
        ("dmSize", ctypes.c_ushort),
        ("dmDriverExtra", ctypes.c_ushort),
        ("dmFields", ctypes.c_ulong),
        ("dmPositionX", ctypes.c_long),
        ("dmPositionY", ctypes.c_long),
        ("dmDisplayOrientation", ctypes.c_ulong),
        ("dmDisplayFixedOutput", ctypes.c_ulong),
        ("dmColor", ctypes.c_short),
        ("dmDuplex", ctypes.c_short),
        ("dmYResolution", ctypes.c_short),
        ("dmTTOption", ctypes.c_short),
        ("dmCollate", ctypes.c_short),
        ("dmFormName", ctypes.c_wchar * 32),
        ("dmLogPixels", ctypes.c_ushort),
        ("dmBitsPerPel", ctypes.c_ulong),
        ("dmPelsWidth", ctypes.c_ulong),
        ("dmPelsHeight", ctypes.c_ulong),
        ("dmDisplayFlags", ctypes.c_ulong),
        ("dmDisplayFrequency", ctypes.c_ulong),
    ]


class _DISPLAY_DEVICE(ctypes.Structure):
    _fields_ = [
        ("cb", wintypes.DWORD),
        ("DeviceName", ctypes.c_wchar * 32),
        ("DeviceString", ctypes.c_wchar * 128),
        ("StateFlags", wintypes.DWORD),
        ("DeviceID", ctypes.c_wchar * 128),
        ("DeviceKey", ctypes.c_wchar * 128),
    ]


DM_PELSWIDTH, DM_PELSHEIGHT, DM_DISPLAYFREQUENCY = 0x80000, 0x100000, 0x400000
ENUM_CURRENT_SETTINGS = -1
CDS_TEST = 0x2
DISP_CHANGE_SUCCESSFUL = 0
DISPLAY_DEVICE_ATTACHED_TO_DESKTOP = 0x1


class DisplayResolutionManager:
    """List monitors by device name and read/set their resolution and refresh rate."""

    def list_devices(self) -> Dict:
        """Enumerate Windows display device names (e.g. '\\\\.\\DISPLAY1')
        for every monitor currently attached to the desktop, with each
        one's friendly adapter/monitor string."""
        try:
            devices: List[Dict] = []
            i = 0
            while True:
                dd = _DISPLAY_DEVICE()
                dd.cb = ctypes.sizeof(_DISPLAY_DEVICE)
                if not ctypes.windll.user32.EnumDisplayDevicesW(None, i, ctypes.byref(dd), 0):
                    break
                if dd.StateFlags & DISPLAY_DEVICE_ATTACHED_TO_DESKTOP:
                    devices.append({"device_name": dd.DeviceName, "adapter": dd.DeviceString})
                i += 1
            return {"devices": devices, "count": len(devices)}
        except Exception as e:
            return {"error": str(e)}

    def _get_devmode(self, device_name: Optional[str], mode_index: int = ENUM_CURRENT_SETTINGS) -> Optional[_DEVMODE]:
        devmode = _DEVMODE()
        devmode.dmSize = ctypes.sizeof(_DEVMODE)
        ok = ctypes.windll.user32.EnumDisplaySettingsW(device_name, mode_index, ctypes.byref(devmode))
        return devmode if ok else None

    def get_resolution(self, device_name: str = None) -> Dict:
        """Get a monitor's current resolution and refresh rate.
        device_name=None targets the primary display."""
        try:
            devmode = self._get_devmode(device_name)
            if devmode is None:
                return {"error": f"Could not read settings for device '{device_name or 'primary'}'."}
            return {
                "width": devmode.dmPelsWidth,
                "height": devmode.dmPelsHeight,
                "refresh_rate_hz": devmode.dmDisplayFrequency,
                "device_name": device_name or "primary",
            }
        except Exception as e:
            return {"error": str(e)}

    def list_supported_modes(self, device_name: str = None) -> Dict:
        """List every distinct (width, height, refresh_rate) combination
        the given monitor reports supporting."""
        try:
            modes = set()
            i = 0
            while True:
                devmode = self._get_devmode(device_name, i)
                if devmode is None:
                    break
                modes.add((devmode.dmPelsWidth, devmode.dmPelsHeight, devmode.dmDisplayFrequency))
                i += 1
            sorted_modes = sorted(modes, key=lambda m: (-m[0], -m[1], -m[2]))
            return {
                "device_name": device_name or "primary",
                "modes": [{"width": w, "height": h, "refresh_rate_hz": r} for w, h, r in sorted_modes],
                "count": len(sorted_modes),
            }
        except Exception as e:
            return {"error": str(e)}

    def set_resolution(
        self, width: int, height: int, device_name: str = None, refresh_rate_hz: int = None, confirm: bool = False
    ) -> Dict:
        """Set a monitor's resolution (and optionally refresh rate).
        device_name=None targets the primary display. Tested with
        CDS_TEST first - rejected cleanly if unsupported rather than
        risking a blank/garbled screen. Not confirm-gated (matches
        windows/display/monitor.py's precedent for the same action)."""
        try:
            devmode = self._get_devmode(device_name)
            if devmode is None:
                return {"error": f"Could not read current settings for device '{device_name or 'primary'}'."}
            devmode.dmPelsWidth = width
            devmode.dmPelsHeight = height
            devmode.dmFields = DM_PELSWIDTH | DM_PELSHEIGHT
            if refresh_rate_hz:
                devmode.dmDisplayFrequency = refresh_rate_hz
                devmode.dmFields |= DM_DISPLAYFREQUENCY

            test_result = ctypes.windll.user32.ChangeDisplaySettingsExW(
                device_name, ctypes.byref(devmode), None, CDS_TEST, None
            )
            if test_result != DISP_CHANGE_SUCCESSFUL:
                return {
                    "error": f"{width}x{height}"
                    f"{f'@{refresh_rate_hz}Hz' if refresh_rate_hz else ''} is not supported by "
                    f"'{device_name or 'primary'}' (test failed, code {test_result})."
                }

            result = ctypes.windll.user32.ChangeDisplaySettingsExW(device_name, ctypes.byref(devmode), None, 0, None)
            if result == DISP_CHANGE_SUCCESSFUL:
                return {
                    "success": True,
                    "device_name": device_name or "primary",
                    "width": width,
                    "height": height,
                    "refresh_rate_hz": refresh_rate_hz,
                }
            return {"error": f"Failed to change resolution (code {result})"}
        except Exception as e:
            return {"error": str(e)}

    def set_refresh_rate(self, refresh_rate_hz: int, device_name: str = None, confirm: bool = False) -> Dict:
        """Set a monitor's refresh rate while keeping its current
        resolution. Not confirm-gated."""
        current = self.get_resolution(device_name)
        if "error" in current:
            return current
        return self.set_resolution(
            current["width"], current["height"], device_name=device_name, refresh_rate_hz=refresh_rate_hz
        )
