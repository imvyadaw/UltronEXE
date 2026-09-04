"""
Send Message
============
Clicks a message-box coordinate, types text, and optionally presses
Enter - the generic, coordinate-based fallback for sending a message
in whatever app is currently open and on-screen. Two other paths
already cover this better when they apply, and this module is
deliberately the last resort behind both:

  1. A dedicated apps/communication/*.py class from Phase 6
     (whatsapp.py, telegram.py, slack.py, ...) - these find their
     app's actual input control instead of a hardcoded coordinate, and
     `ai/prompts/system_prompts.py` already tells the model to prefer
     them. Use this module only for an app that has no dedicated class.
  2. A CONNECT/*.py module (this same phase) - those send through a
     real API/protocol with no on-screen app required at all. Prefer
     CONNECT/whatsapp.py over this module for WhatsApp specifically,
     for example.

Builds on click_mouse.py + type_text.py the same way fill_form.py
does, imported lazily for the same reason.
"""

from typing import Dict, Optional

DEFAULT_TYPE_DELAY_SECONDS = 0.1


class SendMessage:
    """Generic coordinate-based message send. Use get_send_message()."""

    def is_available(self) -> bool:
        try:
            from actions.click_mouse import get_click_mouse
            from actions.type_text import get_type_text

            return get_click_mouse().is_available() and get_type_text().is_available()
        except Exception:
            return False

    def send(self, text: str, input_x: int, input_y: int, press_enter: bool = True) -> Dict:
        """Clicks (`input_x`, `input_y`) - expected to be the
        message box of whatever chat app is currently open - types
        `text`, and presses Enter unless `press_enter` is False.
        Returns {"success": bool, "error": Optional[str]}."""
        if not text:
            return {"success": False, "error": "no text given"}
        try:
            from actions.click_mouse import get_click_mouse
            from actions.type_text import get_type_text
        except Exception:
            return {"success": False, "error": "ACTIONS primitives unavailable"}

        clicker = get_click_mouse()
        typer = get_type_text()
        if not (clicker.is_available() and typer.is_available()):
            return {"success": False, "error": "pyautogui not available"}

        click_result = clicker.click(input_x, input_y)
        if not click_result["success"]:
            return {"success": False, "error": click_result["error"]}

        type_result = typer.type_text(text)
        if not type_result["success"]:
            return {"success": False, "error": type_result["error"]}

        if press_enter:
            try:
                import pyautogui

                pyautogui.press("enter")
            except Exception as exc:
                return {"success": False, "error": f"typed but Enter failed: {exc}"}

        return {"success": True, "error": None}


_send_message: Optional[SendMessage] = None


def get_send_message() -> SendMessage:
    global _send_message
    if _send_message is None:
        _send_message = SendMessage()
    return _send_message
