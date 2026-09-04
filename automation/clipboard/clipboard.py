"""Clipboard control
==================
Read/write the system clipboard.
"""

from typing import Dict

try:
    import pyperclip

    HAS_PYPERCLIP = True
except ImportError:
    HAS_PYPERCLIP = False


class ClipboardControl:
    """Read/write the system clipboard."""

    def get_clipboard(self) -> Dict:
        """Get current clipboard text."""
        if not HAS_PYPERCLIP:
            return {"error": "pyperclip not installed - run: pip install pyperclip"}
        try:
            return {"clipboard": pyperclip.paste()}
        except Exception as e:
            return {"error": str(e)}

    def set_clipboard(self, text: str) -> Dict:
        """Copy text to the clipboard."""
        if not HAS_PYPERCLIP:
            return {"error": "pyperclip not installed - run: pip install pyperclip"}
        try:
            pyperclip.copy(text)
            return {"success": True, "copied_to_clipboard": text}
        except Exception as e:
            return {"error": str(e)}
