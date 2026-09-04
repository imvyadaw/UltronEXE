"""Display monitor control
========================
Screenshots, display sleep, brightness control, and multi-monitor
info (enumerate connected monitors, get/set resolution).

Renamed from display/display.py (DisplayControl) as part of Phase 8's
windows/ restructure. Only windows/__init__.py imported the old
module, so this is a clean rename. Adds list_monitors/get_resolution/
set_resolution to actually earn the "monitor" name (the old file only
covered screenshots/sleep/brightness).
"""

import ctypes
from ctypes import wintypes
from pathlib import Path
from typing import Dict
from datetime import datetime

try:
    from PIL import ImageGrab

    HAS_PIL = True
except ImportError:
    HAS_PIL = False

try:
    import screen_brightness_control as sbc

    HAS_SBC = True
except ImportError:
    HAS_SBC = False

try:
    import win32api

    HAS_WIN32API = True
except ImportError:
    HAS_WIN32API = False


class DisplayMonitor:
    """Screenshots, display sleep, brightness, and multi-monitor control."""

    def __init__(self):
        self.home_dir = Path.home()

    def take_screenshot(self, filename: str = None) -> Dict:
        """Take a screenshot and save it to the Desktop."""
        if not HAS_PIL:
            return {"error": "Pillow not installed - run: pip install Pillow"}
        try:
            if not filename:
                filename = f"screenshot_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
            filepath = str(self.home_dir / "Desktop" / filename)
            ImageGrab.grab().save(filepath)
            return {"success": True, "saved_to": filepath}
        except Exception as e:
            return {"error": str(e)}

    def sleep_display(self) -> Dict:
        """Turn off the monitor."""
        try:
            HWND_BROADCAST = 0xFFFF
            WM_SYSCOMMAND = 0x0112
            SC_MONITORPOWER = 0xF170
            MONITOR_OFF = 2
            ctypes.windll.user32.SendMessageW(HWND_BROADCAST, WM_SYSCOMMAND, SC_MONITORPOWER, MONITOR_OFF)
            return {"success": True, "message": "Display sleeping"}
        except Exception as e:
            return {"error": str(e)}

    def get_brightness(self) -> Dict:
        """Get current screen brightness (0-100)."""
        if not HAS_SBC:
            return {"error": "screen_brightness_control not installed - run: pip install screen_brightness_control"}
        try:
            levels = sbc.get_brightness()
            return {"brightness": levels[0] if levels else None}
        except Exception as e:
            return {"error": str(e)}

    def set_brightness(self, level: int) -> Dict:
        """Set screen brightness (0-100)."""
        if not HAS_SBC:
            return {"error": "screen_brightness_control not installed - run: pip install screen_brightness_control"}
        try:
            level = max(0, min(100, level))
            sbc.set_brightness(level)
            return {"success": True, "brightness": level}
        except Exception as e:
            return {"error": str(e)}

    def list_monitors(self) -> Dict:
        """Enumerate connected monitors with their resolution and position."""
        try:
            monitors = []
            MONITORINFOF_PRIMARY = 0x1

            def _callback(hmonitor, hdc, lprect, lparam):
                info = win32api.GetMonitorInfo(hmonitor) if HAS_WIN32API else None
                if info:
                    rect = info["Monitor"]
                    monitors.append(
                        {
                            "device": info.get("Device"),
                            "primary": bool(info.get("Flags", 0) & MONITORINFOF_PRIMARY),
                            "left": rect[0],
                            "top": rect[1],
                            "right": rect[2],
                            "bottom": rect[3],
                            "width": rect[2] - rect[0],
                            "height": rect[3] - rect[1],
                        }
                    )
                return True

            if HAS_WIN32API:
                MonitorEnumProc = ctypes.WINFUNCTYPE(
                    ctypes.c_int, ctypes.c_ulong, ctypes.c_ulong, ctypes.POINTER(wintypes.RECT), ctypes.c_double
                )
                ctypes.windll.user32.EnumDisplayMonitors(0, 0, MonitorEnumProc(_callback), 0)
                if monitors:
                    return {"count": len(monitors), "monitors": monitors}

            # Fallback: just report the virtual screen size (all monitors combined)
            width = ctypes.windll.user32.GetSystemMetrics(78)  # SM_CXVIRTUALSCREEN
            height = ctypes.windll.user32.GetSystemMetrics(79)  # SM_CYVIRTUALSCREEN
            count = ctypes.windll.user32.GetSystemMetrics(80)  # SM_CMONITORS
            return {
                "count": count,
                "note": "pywin32 not installed - showing combined virtual screen only",
                "virtual_screen": {"width": width, "height": height},
            }
        except Exception as e:
            return {"error": str(e)}

    def get_resolution(self) -> Dict:
        """Get the primary display's current resolution."""
        try:
            width = ctypes.windll.user32.GetSystemMetrics(0)  # SM_CXSCREEN
            height = ctypes.windll.user32.GetSystemMetrics(1)  # SM_CYSCREEN
            return {"width": width, "height": height}
        except Exception as e:
            return {"error": str(e)}

    def set_resolution(self, width: int, height: int) -> Dict:
        """Set the primary display's resolution (falls back to nearest supported mode)."""
        try:

            class DEVMODE(ctypes.Structure):
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

            DM_PELSWIDTH = 0x80000
            DM_PELSHEIGHT = 0x100000
            ENUM_CURRENT_SETTINGS = -1
            CDS_TEST = 0x2
            DISP_CHANGE_SUCCESSFUL = 0

            devmode = DEVMODE()
            devmode.dmSize = ctypes.sizeof(DEVMODE)
            ctypes.windll.user32.EnumDisplaySettingsW(None, ENUM_CURRENT_SETTINGS, ctypes.byref(devmode))
            devmode.dmPelsWidth = width
            devmode.dmPelsHeight = height
            devmode.dmFields = DM_PELSWIDTH | DM_PELSHEIGHT

            test_result = ctypes.windll.user32.ChangeDisplaySettingsW(ctypes.byref(devmode), CDS_TEST)
            if test_result != DISP_CHANGE_SUCCESSFUL:
                return {
                    "error": f"Resolution {width}x{height} is not supported by this display (test failed, code {test_result})"
                }

            result = ctypes.windll.user32.ChangeDisplaySettingsW(ctypes.byref(devmode), 0)
            if result == DISP_CHANGE_SUCCESSFUL:
                return {"success": True, "width": width, "height": height}
            return {"error": f"Failed to change resolution (code {result})"}
        except Exception as e:
            return {"error": str(e)}
