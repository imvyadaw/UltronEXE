"""
Snipping Tool automation
===========================
capture_screen()/capture_region() take the screenshot directly via
pyautogui (far more reliable than driving the Snipping Tool UI's
click-and-drag selection); open() still launches the visible tool for
the user to do a manual, interactive snip.
"""

import time
from typing import Dict, Optional

from apps.base_app import BaseApp

try:
    import pyautogui

    HAS_PYAUTOGUI = True
except ImportError:
    HAS_PYAUTOGUI = False


class SnippingToolApp(BaseApp):
    """Open the Snipping Tool, or capture the screen/a region directly."""

    APP_NAME = "snipping tool"
    PROCESS_NAMES = ["snippingtool.exe", "screenclipping.exe"]
    EXE_HINTS = ["snippingtool", "snippingtool.exe"]

    def capture_screen(self, save_path: Optional[str] = None) -> Dict:
        if not HAS_PYAUTOGUI:
            return {"error": "pyautogui not installed - run: pip install pyautogui"}
        try:
            from config import BASE_DIR

            path = save_path or str(BASE_DIR / "storage" / "exports" / f"screenshot_{int(time.time())}.png")
            import os

            os.makedirs(os.path.dirname(path), exist_ok=True)
            pyautogui.screenshot(path)
            return {"success": True, "path": path}
        except Exception as e:
            return {"error": str(e)}

    def capture_region(self, x: int, y: int, width: int, height: int, save_path: Optional[str] = None) -> Dict:
        if not HAS_PYAUTOGUI:
            return {"error": "pyautogui not installed - run: pip install pyautogui"}
        try:
            from config import BASE_DIR

            path = save_path or str(BASE_DIR / "storage" / "exports" / f"screenshot_{int(time.time())}.png")
            import os

            os.makedirs(os.path.dirname(path), exist_ok=True)
            pyautogui.screenshot(path, region=(x, y, width, height))
            return {"success": True, "path": path}
        except Exception as e:
            return {"error": str(e)}

    def open_interactive(self) -> Dict:
        """Windows key + Shift + S starts an interactive region snip."""
        return self.press_key("win+shift+s")
