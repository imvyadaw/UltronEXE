"""Keyboard automation
====================
Type text and press key combos system-wide.
"""

from typing import Dict

try:
    import pyautogui

    pyautogui.FAILSAFE = False
    HAS_PYAUTOGUI = True
except ImportError:
    HAS_PYAUTOGUI = False


class KeyboardControl:
    """Type text / press key combinations anywhere on the system."""

    def type_text(self, text: str) -> Dict:
        """Type text into whatever window/field is currently focused."""
        if not HAS_PYAUTOGUI:
            return {"error": "pyautogui not installed - run: pip install pyautogui"}
        try:
            pyautogui.typewrite(text, interval=0.01)
            return {"success": True, "typed": text}
        except Exception as e:
            return {"error": str(e)}

    def press_key(self, key: str) -> Dict:
        """Press a key or combo (e.g. 'enter', 'ctrl+s') in the focused window."""
        if not HAS_PYAUTOGUI:
            return {"error": "pyautogui not installed - run: pip install pyautogui"}
        try:
            if "+" in key:
                pyautogui.hotkey(*[k.strip().lower() for k in key.split("+")])
            else:
                pyautogui.press(key.lower())
            return {"success": True, "key": key}
        except Exception as e:
            return {"error": str(e)}
