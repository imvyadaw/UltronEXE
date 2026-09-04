"""Taskbar Manager
==================
Reads and controls Windows taskbar layout and behavior - the settings
under Settings > Personalization > Taskbar. Per-user registry:
HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Explorer\\Advanced
(icon alignment, small icons, widgets, task view button) and
...\\Explorer\\Advanced\\Search (search box mode). No admin needed for
any of it.

Auto-hide is handled separately via the live Windows shell APIs
(SHAppBarMessage) rather than a registry value, so it takes effect
immediately without an Explorer restart.

Distinct from start_menu_manager.py (Start menu content/pinning) and
from the top-level ui/ package (ULTRON's own tray/overlay, not the
Windows taskbar).

Every setter here is a per-user cosmetic/layout preference - not
confirm-gated. Registry changes to Explorer\\Advanced generally need
Explorer restarted (or sign-out) to visibly apply; restart_explorer()
does that on request.
"""

import ctypes
import subprocess
from typing import Dict, Optional


class TaskbarManager:
    """Inspect and control Windows taskbar alignment, icon size, search box, widgets, and auto-hide."""

    _ADV_KEY = r"HKCU\Software\Microsoft\Windows\CurrentVersion\Explorer\Advanced"
    _SEARCH_KEY = r"HKCU\Software\Microsoft\Windows\CurrentVersion\Search"

    _SEARCH_MODES = {"hidden": 0, "icon": 1, "icon_and_label": 2, "box": 3}

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
        script = f'(Get-ItemProperty -Path "Registry::{key}" -Name {name} -ErrorAction SilentlyContinue).{name}'
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
            f'Set-ItemProperty -Path "Registry::{key}" -Name {name} -Value {value} -Type DWord -Force'
        )
        result = self._run_ps(script)
        if "error" in result:
            return result
        if not result["success"]:
            return {"error": result["stderr"] or f"Failed to set {name}."}
        return {"success": True}

    def get_settings(self) -> Dict:
        """Read current taskbar alignment, small-icons, widgets, task
        view button, and search box mode."""
        align = self._read_dword(self._ADV_KEY, "TaskbarAl")
        small = self._read_dword(self._ADV_KEY, "TaskbarSi")
        widgets = self._read_dword(self._ADV_KEY, "TaskbarDa")
        task_view = self._read_dword(self._ADV_KEY, "ShowTaskViewButton")
        search_mode = self._read_dword(self._SEARCH_KEY, "SearchboxTaskbarMode")
        mode_name = next((k for k, v in self._SEARCH_MODES.items() if v == search_mode), None)
        return {
            "alignment": "center" if align == 1 else ("left" if align == 0 else None),
            "small_icons": (small == 0) if small is not None else None,
            "widgets_visible": bool(widgets) if widgets is not None else None,
            "task_view_button_visible": bool(task_view) if task_view is not None else None,
            "search_box_mode": mode_name,
        }

    def set_alignment(self, position: str, confirm: bool = False) -> Dict:
        """Set taskbar icon alignment: 'left' or 'center' (Windows 11).
        Not confirm-gated. Explorer restart not required - applies live."""
        if position not in ("left", "center"):
            return {"error": "position must be 'left' or 'center'."}
        result = self._write_dword(self._ADV_KEY, "TaskbarAl", 1 if position == "center" else 0)
        if "error" in result:
            return result
        return {"success": True, "alignment": position, "note": "Explorer restart may be needed on some builds."}

    def set_small_icons(self, enabled: bool, confirm: bool = False) -> Dict:
        """Turn small taskbar icons on/off. Not confirm-gated. Requires
        an Explorer restart to visibly apply - see restart_explorer()."""
        result = self._write_dword(self._ADV_KEY, "TaskbarSi", 0 if enabled else 1)
        if "error" in result:
            return result
        return {"success": True, "small_icons": enabled, "note": "Call restart_explorer() to apply immediately."}

    def set_search_box_mode(self, mode: str, confirm: bool = False) -> Dict:
        """Set the taskbar search box display: 'hidden', 'icon',
        'icon_and_label', or 'box'. Not confirm-gated. Requires an
        Explorer restart to visibly apply."""
        if mode not in self._SEARCH_MODES:
            return {"error": f"mode must be one of {list(self._SEARCH_MODES)}."}
        result = self._write_dword(self._SEARCH_KEY, "SearchboxTaskbarMode", self._SEARCH_MODES[mode])
        if "error" in result:
            return result
        return {"success": True, "search_box_mode": mode, "note": "Call restart_explorer() to apply immediately."}

    def set_widgets_visible(self, enabled: bool, confirm: bool = False) -> Dict:
        """Show/hide the Widgets icon on the taskbar. Not confirm-gated."""
        result = self._write_dword(self._ADV_KEY, "TaskbarDa", 1 if enabled else 0)
        if "error" in result:
            return result
        return {"success": True, "widgets_visible": enabled, "note": "Explorer restart may be needed on some builds."}

    def set_task_view_visible(self, enabled: bool, confirm: bool = False) -> Dict:
        """Show/hide the Task View button on the taskbar. Not confirm-gated."""
        result = self._write_dword(self._ADV_KEY, "ShowTaskViewButton", 1 if enabled else 0)
        if "error" in result:
            return result
        return {"success": True, "task_view_button_visible": enabled}

    def get_autohide(self) -> Dict:
        """Read whether the taskbar is set to auto-hide, via the live
        shell APPBARDATA state (not the registry)."""
        state = self._query_autohide_state()
        if state is None:
            return {"error": "Could not query taskbar state - this is only available on Windows."}
        return {"auto_hide": bool(state & 0x1)}

    def set_autohide(self, enabled: bool, confirm: bool = False) -> Dict:
        """Turn taskbar auto-hide on/off immediately via the live shell
        APPBARDATA API (SHAppBarMessage) - no registry write, no
        Explorer restart needed. Not confirm-gated."""
        try:

            class APPBARDATA(ctypes.Structure):
                _fields_ = [
                    ("cbSize", ctypes.c_ulong),
                    ("hWnd", ctypes.c_void_p),
                    ("uCallbackMessage", ctypes.c_uint),
                    ("uEdge", ctypes.c_uint),
                    ("rc", ctypes.c_long * 4),
                    ("lParam", ctypes.c_long),
                ]

            ABM_SETSTATE = 0x0000000A
            ABS_AUTOHIDE = 0x1
            abd = APPBARDATA()
            abd.cbSize = ctypes.sizeof(APPBARDATA)
            abd.lParam = ABS_AUTOHIDE if enabled else 0
            ctypes.windll.shell32.SHAppBarMessage(ABM_SETSTATE, ctypes.byref(abd))
            return {"success": True, "auto_hide": enabled}
        except AttributeError:
            return {"error": "ctypes.windll is only available on Windows."}
        except Exception as e:
            return {"error": str(e)}

    def _query_autohide_state(self) -> Optional[int]:
        try:

            class APPBARDATA(ctypes.Structure):
                _fields_ = [
                    ("cbSize", ctypes.c_ulong),
                    ("hWnd", ctypes.c_void_p),
                    ("uCallbackMessage", ctypes.c_uint),
                    ("uEdge", ctypes.c_uint),
                    ("rc", ctypes.c_long * 4),
                    ("lParam", ctypes.c_long),
                ]

            ABM_GETSTATE = 0x00000004
            abd = APPBARDATA()
            abd.cbSize = ctypes.sizeof(APPBARDATA)
            state = ctypes.windll.shell32.SHAppBarMessage(ABM_GETSTATE, ctypes.byref(abd))
            return state
        except AttributeError:
            return None
        except Exception:
            return None

    def restart_explorer(self, confirm: bool = False) -> Dict:
        """Restart explorer.exe to apply registry-based taskbar settings
        that don't take effect live (icon size, search box mode, some
        builds' alignment/widgets changes). Confirm-gated - it briefly
        closes the desktop shell, minimizing open windows momentarily."""
        if not confirm:
            return {
                "requires_confirmation": True,
                "preview": "This will restart explorer.exe (the desktop/taskbar shell) to apply pending settings. The desktop and taskbar will briefly disappear and reappear; open app windows are not closed.",
            }
        result = self._run_ps("Stop-Process -Name explorer -Force; Start-Process explorer")
        if "error" in result:
            return result
        return {"success": True, "message": "Explorer restarted."}
