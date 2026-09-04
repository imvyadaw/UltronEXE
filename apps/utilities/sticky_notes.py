"""Sticky Notes automation."""

import time
from typing import Dict

from apps.base_app import BaseApp


class StickyNotesApp(BaseApp):
    """Open Sticky Notes and create a new note with text."""

    APP_NAME = "sticky notes"
    PROCESS_NAMES = ["stickynotes.exe", "microsoft.notes"]
    EXE_HINTS = []

    def new_note(self, text: str) -> Dict:
        opened = self.open()
        if opened.get("error"):
            return opened
        time.sleep(1.2)
        self.press_key("ctrl+n")
        time.sleep(0.3)
        return self.type_text(text)
