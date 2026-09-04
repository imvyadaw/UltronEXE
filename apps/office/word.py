"""
Microsoft Word automation
===========================
GUI-level control (open/new/save/print/close via the real winword.exe and
keyboard shortcuts). For headless document *creation/editing* without
Word installed, see files/office/office.py (python-docx based) instead -
this module drives the actual application window.
"""

import time
from typing import Dict

from apps.base_app import BaseApp


class WordApp(BaseApp):
    """Open, edit, save, and print .docx files via Microsoft Word."""

    APP_NAME = "word"
    PROCESS_NAMES = ["winword.exe", "winword"]
    EXE_HINTS = ["winword", "winword.exe"]

    def open_file(self, path: str) -> Dict:
        exe = self.resolve_executable()
        if exe:
            return self.run_command([exe, path])
        try:
            import os

            os.startfile(path)
            return {"success": True, "path": path}
        except Exception as e:
            return {"error": str(e)}

    def new_document(self) -> Dict:
        return self.open()

    def save(self) -> Dict:
        focused = self.focus()
        if focused.get("error"):
            return focused
        time.sleep(0.3)
        return self.press_key("ctrl+s")

    def save_as(self, path: str) -> Dict:
        """Opens the Save As dialog and types the path - the dialog still
        needs a final Enter, left to the caller/next tool call since
        typing too fast into an unconfirmed dialog is unreliable."""
        focused = self.focus()
        if focused.get("error"):
            return focused
        time.sleep(0.3)
        self.press_key("f12")
        time.sleep(0.5)
        typed = self.type_text(path)
        return (
            typed
            if typed.get("error")
            else {"success": True, "path": path, "note": "press Enter to confirm the Save As dialog"}
        )

    def print_document(self) -> Dict:
        focused = self.focus()
        if focused.get("error"):
            return focused
        time.sleep(0.3)
        return self.press_key("ctrl+p")

    def close_document(self) -> Dict:
        focused = self.focus()
        if focused.get("error"):
            return focused
        time.sleep(0.3)
        return self.press_key("ctrl+w")
