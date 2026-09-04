"""
Click Mouse
===========
Moves to and clicks a screen coordinate, via `pyautogui`. The other
half of type_text.py's primitive pair - fill_form.py and
send_message.py both click a field with this module before typing
into it with that one. Coordinate-based on purpose: this project's
gesture-control layer (MediaPipe, per the ULTRON profile) and vision
phases are what would supply a target's coordinates in the first
place, so this module doesn't duplicate any element-finding logic of
its own.

Same optional-dependency contract as type_text.py: no `pyautogui`, or
any call failure, collapses to {"success": False, "error": ...}
rather than an exception.
"""

from typing import Dict, Optional

try:
    import pyautogui

    _PYAUTOGUI_AVAILABLE = True
except Exception:
    _PYAUTOGUI_AVAILABLE = False


class ClickMouse:
    """Generic coordinate-based mouse control. Use get_click_mouse()."""

    def is_available(self) -> bool:
        return _PYAUTOGUI_AVAILABLE

    def click(self, x: int, y: int, button: str = "left", clicks: int = 1) -> Dict:
        """Moves to (`x`, `y`) and clicks. `button` is "left",
        "right", or "middle"; `clicks` lets a caller ask for a
        double-click (2) without a separate method. Returns
        {"success": bool, "error": Optional[str]}."""
        if not self.is_available():
            return {"success": False, "error": "pyautogui not available"}
        try:
            pyautogui.click(x=x, y=y, button=button, clicks=max(1, clicks))
            return {"success": True, "error": None}
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    def move(self, x: int, y: int) -> Dict:
        """Moves the cursor to (`x`, `y`) without clicking. Returns
        {"success": bool, "error": Optional[str]}."""
        if not self.is_available():
            return {"success": False, "error": "pyautogui not available"}
        try:
            pyautogui.moveTo(x, y)
            return {"success": True, "error": None}
        except Exception as exc:
            return {"success": False, "error": str(exc)}


_click_mouse: Optional[ClickMouse] = None


def get_click_mouse() -> ClickMouse:
    global _click_mouse
    if _click_mouse is None:
        _click_mouse = ClickMouse()
    return _click_mouse
