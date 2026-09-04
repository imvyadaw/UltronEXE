"""Virtual desktop manager
========================
Create, switch between, and close Windows 10/11 virtual desktops.
Uses the `pyvda` library (wraps the undocumented Windows Virtual
Desktop COM APIs) when available; otherwise falls back to simulating
the built-in keyboard shortcuts (Win+Ctrl+Right/Left/D/F4) via
pyautogui, which covers switching/creating/closing even without the
extra dependency, just without the ability to enumerate desktops by name.
"""

from typing import Dict

try:
    from pyvda import VirtualDesktop, get_virtual_desktops, AppView

    HAS_PYVDA = True
except ImportError:
    HAS_PYVDA = False

try:
    import pyautogui

    pyautogui.FAILSAFE = False
    HAS_PYAUTOGUI = True
except ImportError:
    HAS_PYAUTOGUI = False


class VirtualDesktopManager:
    """Manage Windows virtual desktops."""

    def list_desktops(self) -> Dict:
        """List all virtual desktops with their index and (if named) name."""
        if not HAS_PYVDA:
            return {
                "error": "pyvda not installed - run: pip install pyvda (falls back to keyboard-shortcut-only mode without it)"
            }
        try:
            desktops = get_virtual_desktops()
            current = VirtualDesktop.current()
            return {
                "count": len(desktops),
                "current_number": current.number,
                "desktops": [{"number": d.number, "name": getattr(d, "name", None)} for d in desktops],
            }
        except Exception as e:
            return {"error": str(e)}

    def create_desktop(self) -> Dict:
        """Create a new virtual desktop."""
        if HAS_PYVDA:
            try:
                VirtualDesktop.create()
                return {"success": True, "method": "pyvda"}
            except Exception as e:
                return {"error": str(e)}
        if HAS_PYAUTOGUI:
            pyautogui.hotkey("win", "ctrl", "d")
            return {
                "success": True,
                "method": "keyboard_shortcut",
                "note": "Created via Win+Ctrl+D; cannot confirm the resulting desktop number without pyvda",
            }
        return {"error": "Neither pyvda nor pyautogui installed"}

    def switch_to(self, desktop_number: int) -> Dict:
        """Switch to a virtual desktop by its 1-based index."""
        if HAS_PYVDA:
            try:
                VirtualDesktop(desktop_number).go()
                return {"success": True, "switched_to": desktop_number, "method": "pyvda"}
            except Exception as e:
                return {"error": str(e)}
        if HAS_PYAUTOGUI:
            # No absolute-jump shortcut without pyvda; step with Right/Left
            # relative to desktop 1 as a best-effort approximation.
            for _ in range(max(0, desktop_number - 1)):
                pyautogui.hotkey("win", "ctrl", "right")
            return {
                "success": True,
                "method": "keyboard_shortcut",
                "note": "Approximate: stepped right from desktop 1, cannot confirm exact landing without pyvda",
            }
        return {"error": "Neither pyvda nor pyautogui installed"}

    def switch_next(self) -> Dict:
        if HAS_PYAUTOGUI:
            pyautogui.hotkey("win", "ctrl", "right")
            return {"success": True, "direction": "next"}
        return {"error": "pyautogui not installed"}

    def switch_previous(self) -> Dict:
        if HAS_PYAUTOGUI:
            pyautogui.hotkey("win", "ctrl", "left")
            return {"success": True, "direction": "previous"}
        return {"error": "pyautogui not installed"}

    def close_current_desktop(self) -> Dict:
        """Close the current virtual desktop (windows on it move to the previous desktop)."""
        if HAS_PYVDA:
            try:
                VirtualDesktop.current().remove()
                return {"success": True, "method": "pyvda"}
            except Exception as e:
                return {"error": str(e)}
        if HAS_PYAUTOGUI:
            pyautogui.hotkey("win", "ctrl", "f4")
            return {"success": True, "method": "keyboard_shortcut"}
        return {"error": "Neither pyvda nor pyautogui installed"}

    def move_window_to_desktop(self, window_title: str, desktop_number: int) -> Dict:
        """Move a window (by title match) to a specific virtual desktop."""
        if not HAS_PYVDA:
            return {
                "error": "pyvda not installed - run: pip install pyvda (required for moving specific windows between desktops)"
            }
        try:
            import pygetwindow as gw

            matches = [w for w in gw.getAllWindows() if window_title.lower() in w.title.lower() and w.title.strip()]
            if not matches:
                return {"error": f"No window matching '{window_title}'"}
            hwnd = matches[0]._hWnd
            view = AppView(hwnd=hwnd)
            view.move(VirtualDesktop(desktop_number))
            return {"success": True, "window_title": matches[0].title, "moved_to_desktop": desktop_number}
        except Exception as e:
            return {"error": str(e)}
