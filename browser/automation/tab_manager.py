"""
Generic (hotkey-driven) tab manager
======================================
Browser-agnostic tab actions - new/close/switch/reopen/duplicate - that
work identically in Chrome, Edge, and Firefox because they're all the
same keyboard shortcuts, driven against whichever browser window is
currently focused. This complements browser/tab_manager.py's
TabManager, which instead *lists* tabs per-browser via UI Automation
(accessibility tree) rather than blindly sending keystrokes - use that
one when you need to know what's actually open, and this one to act on
"the current tab" without needing a title/index to target.
"""

import time
from typing import Dict

from browser.automation.automation import BrowserAutomation

try:
    import pyautogui

    pyautogui.FAILSAFE = False
    HAS_PYAUTOGUI = True
except ImportError:
    HAS_PYAUTOGUI = False


class GenericTabManager:
    """Keyboard-shortcut-driven tab control for whichever browser is active."""

    def __init__(self):
        self._browsers = BrowserAutomation()

    def _focus(self, browser: str = None) -> str:
        name = (browser or self._browsers.detect_active_browser()).lower()
        controller = {
            "chrome": self._browsers.chrome,
            "edge": self._browsers.edge,
            "firefox": self._browsers.firefox,
        }.get(name)
        if controller:
            focus_method = getattr(controller, f"_focus_{name}", None)
            if focus_method:
                focus_method()
                time.sleep(0.2)
        return name

    def new_tab(self, url: str = None, browser: str = None) -> Dict:
        if not HAS_PYAUTOGUI:
            return {"error": "pyautogui not installed - run: pip install pyautogui"}
        name = self._focus(browser)
        try:
            pyautogui.hotkey("ctrl", "t")
            if url:
                time.sleep(0.2)
                pyautogui.typewrite(url, interval=0.01)
                pyautogui.press("enter")
            return {"success": True, "browser": name, "url": url}
        except Exception as e:
            return {"error": str(e)}

    def close_current_tab(self, browser: str = None) -> Dict:
        if not HAS_PYAUTOGUI:
            return {"error": "pyautogui not installed - run: pip install pyautogui"}
        name = self._focus(browser)
        try:
            pyautogui.hotkey("ctrl", "w")
            return {"success": True, "browser": name}
        except Exception as e:
            return {"error": str(e)}

    def reopen_closed_tab(self, browser: str = None) -> Dict:
        if not HAS_PYAUTOGUI:
            return {"error": "pyautogui not installed - run: pip install pyautogui"}
        name = self._focus(browser)
        try:
            pyautogui.hotkey("ctrl", "shift", "t")
            return {"success": True, "browser": name}
        except Exception as e:
            return {"error": str(e)}

    def next_tab(self, browser: str = None) -> Dict:
        if not HAS_PYAUTOGUI:
            return {"error": "pyautogui not installed - run: pip install pyautogui"}
        name = self._focus(browser)
        try:
            pyautogui.hotkey("ctrl", "tab")
            return {"success": True, "browser": name}
        except Exception as e:
            return {"error": str(e)}

    def previous_tab(self, browser: str = None) -> Dict:
        if not HAS_PYAUTOGUI:
            return {"error": "pyautogui not installed - run: pip install pyautogui"}
        name = self._focus(browser)
        try:
            pyautogui.hotkey("ctrl", "shift", "tab")
            return {"success": True, "browser": name}
        except Exception as e:
            return {"error": str(e)}

    def go_to_tab(self, index: int, browser: str = None) -> Dict:
        """Ctrl+1..8 jumps to that tab position; Ctrl+9 always jumps to
        the last tab (both real Chromium/Firefox shortcuts)."""
        if not HAS_PYAUTOGUI:
            return {"error": "pyautogui not installed - run: pip install pyautogui"}
        name = self._focus(browser)
        try:
            key = str(min(max(index, 1), 9))
            pyautogui.hotkey("ctrl", key)
            return {"success": True, "browser": name, "index": index}
        except Exception as e:
            return {"error": str(e)}

    def duplicate_tab(self, browser: str = None) -> Dict:
        """Alt+Shift+D duplicates the current tab in every supported
        Chromium/Firefox build."""
        if not HAS_PYAUTOGUI:
            return {"error": "pyautogui not installed - run: pip install pyautogui"}
        name = self._focus(browser)
        try:
            pyautogui.hotkey("alt", "shift", "d")
            return {"success": True, "browser": name}
        except Exception as e:
            return {"error": str(e)}

    def new_window(self, browser: str = None) -> Dict:
        if not HAS_PYAUTOGUI:
            return {"error": "pyautogui not installed - run: pip install pyautogui"}
        name = self._focus(browser)
        try:
            pyautogui.hotkey("ctrl", "n")
            return {"success": True, "browser": name}
        except Exception as e:
            return {"error": str(e)}

    def new_incognito_window(self, browser: str = None) -> Dict:
        """Ctrl+Shift+N (Chrome/Edge incognito, Firefox private window - same shortcut)."""
        if not HAS_PYAUTOGUI:
            return {"error": "pyautogui not installed - run: pip install pyautogui"}
        name = self._focus(browser)
        try:
            pyautogui.hotkey("ctrl", "shift", "n")
            return {"success": True, "browser": name}
        except Exception as e:
            return {"error": str(e)}

    def mute_tab(self, browser: str = None) -> Dict:
        """Chrome/Edge only: M toggles audio mute for the active tab."""
        if not HAS_PYAUTOGUI:
            return {"error": "pyautogui not installed - run: pip install pyautogui"}
        name = self._focus(browser)
        try:
            pyautogui.press("m")
            return {"success": True, "browser": name}
        except Exception as e:
            return {"error": str(e)}
