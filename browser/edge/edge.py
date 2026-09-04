"""Edge automation
================
Tab list/close, scroll, navigate, type, zoom, and YouTube control for
Microsoft Edge - same approach as browser/chrome/chrome.py since Edge
is Chromium-based and shares the same keyboard shortcuts and UI
Automation window class ("Chrome_WidgetWin_1"). We find the specific
Edge window by title first (via pygetwindow) so this doesn't
accidentally grab a Chrome window if both are open.
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


class EdgeController:
    """Edge tab/scroll/navigate/zoom control plus YouTube playback control."""

    def _focus_edge(self) -> bool:
        """Bring the Edge window to the foreground. Returns True if found."""
        if not HAS_PYGETWINDOW:
            return False
        try:
            windows = [w for w in gw.getAllWindows() if "Edge" in w.title and w.title.strip()]
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

    def list_edge_tabs(self) -> Dict:
        """List all open tabs in Edge (via UI Automation)."""
        if not HAS_PYWINAUTO:
            return {"error": "pywinauto not installed - run: pip install pywinauto"}
        try:
            desktop = Desktop(backend="uia")
            edge_windows = [w for w in desktop.windows(class_name="Chrome_WidgetWin_1") if "Edge" in w.window_text()]
            if not edge_windows:
                return {"error": "Edge window not found - is Edge open?"}

            tabs = []
            for i, tab in enumerate(edge_windows[0].descendants(control_type="TabItem")):
                name = tab.window_text()
                if name:
                    tabs.append({"tab": i + 1, "title": name})
            return {"tabs": tabs, "count": len(tabs)}
        except Exception as e:
            return {"error": f"Couldn't read Edge tabs: {e}"}

    def close_edge_tab(self, tab_identifier: str) -> Dict:
        """Close an Edge tab by matching its title."""
        if not HAS_PYWINAUTO or not HAS_PYAUTOGUI:
            return {"error": "pywinauto/pyautogui not installed - run: pip install pywinauto pyautogui"}
        try:
            desktop = Desktop(backend="uia")
            edge_windows = [w for w in desktop.windows(class_name="Chrome_WidgetWin_1") if "Edge" in w.window_text()]
            if not edge_windows:
                return {"error": "Edge window not found - is Edge open?"}

            identifier_lower = tab_identifier.lower()
            for tab in edge_windows[0].descendants(control_type="TabItem"):
                title = tab.window_text()
                if identifier_lower in title.lower():
                    tab.click_input()
                    time.sleep(0.2)
                    pyautogui.hotkey("ctrl", "w")
                    return {"success": True, "closed": title}
            return {"success": False, "error": f"No tab found matching '{tab_identifier}'"}
        except Exception as e:
            return {"error": str(e)}

    def scroll_edge(self, direction: str = "down", amount: int = 300) -> Dict:
        """Scroll in the active Edge tab. Direction: up, down, left, right, top, bottom."""
        if not HAS_PYAUTOGUI:
            return {"error": "pyautogui not installed - run: pip install pyautogui"}
        if not self._focus_edge():
            return {"error": "Edge window not found - is Edge open?"}
        try:
            direction = direction.lower()
            clicks = max(1, amount // 100)
            if direction == "up":
                pyautogui.scroll(clicks)
            elif direction == "down":
                pyautogui.scroll(-clicks)
            elif direction == "top":
                pyautogui.hotkey("ctrl", "home")
            elif direction == "bottom":
                pyautogui.hotkey("ctrl", "end")
            elif direction == "left":
                pyautogui.hscroll(-clicks)
            elif direction == "right":
                pyautogui.hscroll(clicks)
            return {"success": True, "scrolled": direction}
        except Exception as e:
            return {"error": str(e)}

    def edge_navigate(self, action: str) -> Dict:
        """Navigate in Edge: back, forward, refresh, or a URL."""
        if not HAS_PYAUTOGUI:
            return {"error": "pyautogui not installed - run: pip install pyautogui"}
        if not self._focus_edge():
            return {"error": "Edge window not found - is Edge open?"}
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

    def type_in_edge(self, text: str) -> Dict:
        """Type text into the currently focused element in Edge."""
        if not HAS_PYAUTOGUI:
            return {"error": "pyautogui not installed - run: pip install pyautogui"}
        if not self._focus_edge():
            return {"error": "Edge window not found - is Edge open?"}
        try:
            pyautogui.typewrite(text, interval=0.01)
            return {"success": True, "typed": text}
        except Exception as e:
            return {"error": str(e)}

    def edge_zoom(self, action: str) -> Dict:
        """Zoom in/out/reset in Edge."""
        if not HAS_PYAUTOGUI:
            return {"error": "pyautogui not installed - run: pip install pyautogui"}
        if not self._focus_edge():
            return {"error": "Edge window not found - is Edge open?"}
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
