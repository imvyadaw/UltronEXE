"""Microsoft OneNote automation."""

import time
from typing import Dict, Optional

from apps.base_app import BaseApp


class OneNoteApp(BaseApp):
    """Open OneNote and create pages/notes."""

    APP_NAME = "onenote"
    PROCESS_NAMES = ["onenote.exe", "onenote"]
    EXE_HINTS = ["onenote", "onenote.exe"]

    def new_page(self, title: Optional[str] = None) -> Dict:
        opened = self.open()
        if opened.get("error"):
            return opened
        time.sleep(1.5)
        self.press_key("ctrl+n")
        if title:
            time.sleep(0.3)
            self.type_text(title)
            self.press_key("enter")
        return {"success": True, "title": title}

    def quick_note(self, text: str) -> Dict:
        """Windows key + N opens OneNote's Quick Note panel directly."""
        try:
            self.press_key("win+n")
            time.sleep(0.6)
            self.type_text(text)
            return {"success": True, "note": text}
        except Exception as e:
            return {"error": str(e)}
