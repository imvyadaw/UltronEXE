"""Mouse automation
=================
Move, click, drag, and scroll the mouse system-wide.
"""

from typing import Dict

try:
    import pyautogui

    pyautogui.FAILSAFE = False
    HAS_PYAUTOGUI = True
except ImportError:
    HAS_PYAUTOGUI = False


class MouseControl:
    """Move/click/drag/scroll the mouse anywhere on screen."""

    def move_to(self, x: int, y: int, duration: float = 0.2) -> Dict:
        """Move the mouse cursor to screen coordinates (x, y)."""
        if not HAS_PYAUTOGUI:
            return {"error": "pyautogui not installed - run: pip install pyautogui"}
        try:
            pyautogui.moveTo(x, y, duration=duration)
            return {"success": True, "position": [x, y]}
        except Exception as e:
            return {"error": str(e)}

    def click(self, x: int = None, y: int = None, button: str = "left", clicks: int = 1) -> Dict:
        """Click at (x, y), or at the current cursor position if omitted.
        button: 'left', 'right', or 'middle'."""
        if not HAS_PYAUTOGUI:
            return {"error": "pyautogui not installed - run: pip install pyautogui"}
        try:
            if x is not None and y is not None:
                pyautogui.click(x, y, clicks=clicks, button=button)
            else:
                pyautogui.click(clicks=clicks, button=button)
            pos = pyautogui.position()
            return {"success": True, "position": [pos.x, pos.y], "button": button, "clicks": clicks}
        except Exception as e:
            return {"error": str(e)}

    def double_click(self, x: int = None, y: int = None) -> Dict:
        """Double-click at (x, y), or at the current cursor position."""
        return self.click(x, y, button="left", clicks=2)

    def drag_to(self, x: int, y: int, duration: float = 0.5, button: str = "left") -> Dict:
        """Drag from the current cursor position to (x, y)."""
        if not HAS_PYAUTOGUI:
            return {"error": "pyautogui not installed - run: pip install pyautogui"}
        try:
            pyautogui.dragTo(x, y, duration=duration, button=button)
            return {"success": True, "dragged_to": [x, y]}
        except Exception as e:
            return {"error": str(e)}

    def scroll(self, amount: int) -> Dict:
        """Scroll the mouse wheel. Positive scrolls up, negative scrolls down."""
        if not HAS_PYAUTOGUI:
            return {"error": "pyautogui not installed - run: pip install pyautogui"}
        try:
            pyautogui.scroll(amount)
            return {"success": True, "scrolled": amount}
        except Exception as e:
            return {"error": str(e)}

    def get_position(self) -> Dict:
        """Get the current mouse cursor position."""
        if not HAS_PYAUTOGUI:
            return {"error": "pyautogui not installed - run: pip install pyautogui"}
        try:
            pos = pyautogui.position()
            return {"x": pos.x, "y": pos.y}
        except Exception as e:
            return {"error": str(e)}

    def get_screen_size(self) -> Dict:
        """Get the primary screen resolution."""
        if not HAS_PYAUTOGUI:
            return {"error": "pyautogui not installed - run: pip install pyautogui"}
        try:
            size = pyautogui.size()
            return {"width": size.width, "height": size.height}
        except Exception as e:
            return {"error": str(e)}
