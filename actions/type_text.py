"""
Type Text
=========
Types `text` into whatever window currently has OS focus, via
`pyautogui`. A single, deliberately dumb primitive - it doesn't find,
click, or verify a target field first; that's click_mouse.py's job,
and fill_form.py's job to sequence the two together. Every other
ACTIONS/ module that ends up typing something (fill_form.py,
send_message.py) does so by calling this module rather than calling
pyautogui directly, so there's exactly one place that owns the
"is pyautogui even installed" check.

Same optional-dependency contract as the rest of this project: no
`pyautogui` package, or any call failure (no active window, OS denies
input), collapses to {"success": False, "error": ...} rather than an
exception.
"""

from typing import Dict, Optional

try:
    import pyautogui

    _PYAUTOGUI_AVAILABLE = True
except Exception:
    _PYAUTOGUI_AVAILABLE = False

DEFAULT_INTERVAL_SECONDS = 0.02


class TypeText:
    """Generic keystroke injection at the current focus. Use get_type_text()."""

    def is_available(self) -> bool:
        return _PYAUTOGUI_AVAILABLE

    def type_text(self, text: str, interval: float = DEFAULT_INTERVAL_SECONDS) -> Dict:
        """Types `text` at whatever currently has focus, `interval`
        seconds between keystrokes. Returns
        {"success": bool, "error": Optional[str]}. Does not press
        Enter or Tab afterwards - callers that need that (e.g.
        send_message.py) do it themselves as a separate step."""
        if not self.is_available():
            return {"success": False, "error": "pyautogui not available"}
        if not text:
            return {"success": False, "error": "no text given"}
        try:
            pyautogui.typewrite(text, interval=interval)
            return {"success": True, "error": None}
        except Exception as exc:
            return {"success": False, "error": str(exc)}


_type_text: Optional[TypeText] = None


def get_type_text() -> TypeText:
    global _type_text
    if _type_text is None:
        _type_text = TypeText()
    return _type_text
