"""Firefox automation
===================
Tab list/close, scroll, navigate, type, and zoom for Firefox. Same
keyboard-shortcut approach as Chrome/Edge, but Firefox's UI Automation
window class is "MozillaWindowClass" and its accessibility tree is
less consistently exposed than Chromium's - tab listing/closing needs
Firefox's accessibility support enabled (about:config ->
accessibility.force_disabled = 0, default on modern Firefox). If tab
listing comes back empty, that's the most likely cause.
"""

import time
from typing import Dict

try:
    import pygetwindow as gw

    HAS_PYGETWINDOW = True
except ImportError:
    HAS_PYGETWINDOW = False

try:
    import pyautogui

    pyautogui.FAILSAFE = False
    HAS_PYAUTOGUI = True
except ImportError:
    HAS_PYAUTOGUI = False

try:
    from pywinauto import Desktop

    HAS_PYWINAUTO = True
except ImportError:
    HAS_PYWINAUTO = False


class FirefoxController:
    """Firefox tab/scroll/navigate/zoom control."""

    def _focus_firefox(self) -> bool:
        """Bring the Firefox window to the foreground. Returns True if found."""
        if not HAS_PYGETWINDOW:
            return False
        try:
            windows = [w for w in gw.getAllWindows() if "Firefox" in w.title and w.title.strip()]
            if not windows:
                return False
            win = windows[0]
            if win.isMinimized:
                win.restore()
            win.activate()
            time.sleep(0.3)
            return True
        except Exception:
            return False

    def list_firefox_tabs(self) -> Dict:
        """List all open tabs in Firefox (via UI Automation)."""
        if not HAS_PYWINAUTO:
            return {"error": "pywinauto not installed - run: pip install pywinauto"}
        try:
            desktop = Desktop(backend="uia")
            ff_win = desktop.window(class_name="MozillaWindowClass")
            if not ff_win.exists(timeout=2):
                return {"error": "Firefox window not found - is Firefox open?"}

            tabs = []
            for i, tab in enumerate(ff_win.descendants(control_type="TabItem")):
                name = tab.window_text()
                if name:
                    tabs.append({"tab": i + 1, "title": name})

            if not tabs:
                return {
                    "tabs": [],
                    "count": 0,
                    "note": "No tabs found via UI Automation - make sure Firefox accessibility "
                    "support is enabled (about:config -> accessibility.force_disabled = 0)",
                }
            return {"tabs": tabs, "count": len(tabs)}
        except Exception as e:
            return {"error": f"Couldn't read Firefox tabs: {e}"}

    def close_firefox_tab(self, tab_identifier: str) -> Dict:
        """Close a Firefox tab by matching its title."""
        if not HAS_PYWINAUTO or not HAS_PYAUTOGUI:
            return {"error": "pywinauto/pyautogui not installed - run: pip install pywinauto pyautogui"}
        try:
            desktop = Desktop(backend="uia")
            ff_win = desktop.window(class_name="MozillaWindowClass")
            if not ff_win.exists(timeout=2):
                return {"error": "Firefox window not found - is Firefox open?"}

            identifier_lower = tab_identifier.lower()
            for tab in ff_win.descendants(control_type="TabItem"):
                title = tab.window_text()
                if identifier_lower in title.lower():
                    tab.click_input()
                    time.sleep(0.2)
                    pyautogui.hotkey("ctrl", "w")
                    return {"success": True, "closed": title}
            return {"success": False, "error": f"No tab found matching '{tab_identifier}'"}
        except Exception as e:
            return {"error": str(e)}

    def scroll_firefox(self, direction: str = "down", amount: int = 300) -> Dict:
        """Scroll in the active Firefox tab. Direction: up, down, left, right, top, bottom."""
        if not HAS_PYAUTOGUI:
            return {"error": "pyautogui not installed - run: pip install pyautogui"}
        if not self._focus_firefox():
            return {"error": "Firefox window not found - is Firefox open?"}
        try:
            direction = direction.lower()
            clicks = max(1, amount // 100)
            if direction == "up":
                pyautogui.scroll(clicks)
            elif direction == "down":
                pyautogui.scroll(-clicks)
            elif direction == "top":
                pyautogui.hotkey("home")
            elif direction == "bottom":
                pyautogui.hotkey("end")
            elif direction == "left":
                pyautogui.hscroll(-clicks)
            elif direction == "right":
                pyautogui.hscroll(clicks)
            return {"success": True, "scrolled": direction}
        except Exception as e:
            return {"error": str(e)}

    def firefox_navigate(self, action: str) -> Dict:
        """Navigate in Firefox: back, forward, refresh, or a URL."""
        if not HAS_PYAUTOGUI:
            return {"error": "pyautogui not installed - run: pip install pyautogui"}
        if not self._focus_firefox():
            return {"error": "Firefox window not found - is Firefox open?"}
        try:
            action_lower = action.lower()
            if action_lower == "back":
                pyautogui.hotkey("alt", "left")
            elif action_lower == "forward":
                pyautogui.hotkey("alt", "right")
            elif action_lower in ("refresh", "reload"):
                pyautogui.press("f5")
            else:
                url = action if action.startswith(("http://", "https://")) else f"https://{action}"
                pyautogui.hotkey("ctrl", "l")
                time.sleep(0.15)
                pyautogui.typewrite(url, interval=0.01)
                pyautogui.press("enter")
            return {"success": True, "action": action}
        except Exception as e:
            return {"error": str(e)}

    def type_in_firefox(self, text: str) -> Dict:
        """Type text into the currently focused element in Firefox."""
        if not HAS_PYAUTOGUI:
            return {"error": "pyautogui not installed - run: pip install pyautogui"}
        if not self._focus_firefox():
            return {"error": "Firefox window not found - is Firefox open?"}
        try:
            pyautogui.typewrite(text, interval=0.01)
            return {"success": True, "typed": text}
        except Exception as e:
            return {"error": str(e)}

    def firefox_zoom(self, action: str) -> Dict:
        """Zoom in/out/reset in Firefox."""
        if not HAS_PYAUTOGUI:
            return {"error": "pyautogui not installed - run: pip install pyautogui"}
        if not self._focus_firefox():
            return {"error": "Firefox window not found - is Firefox open?"}
        try:
            action_lower = action.lower()
            if action_lower == "in":
                pyautogui.hotkey("ctrl", "+")
            elif action_lower == "out":
                pyautogui.hotkey("ctrl", "-")
            else:
                pyautogui.hotkey("ctrl", "0")
            return {"success": True, "zoom": action}
        except Exception as e:
            return {"error": str(e)}
