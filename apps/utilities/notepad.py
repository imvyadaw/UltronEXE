"""Windows Notepad automation. write_text()/append_text() go straight
to the file for reliability; open_file()/new_note() drive the visible
app for interactive editing."""

import time
from pathlib import Path
from typing import Dict

from apps.base_app import BaseApp


class NotepadApp(BaseApp):
    """Open, write, and append plain-text files via Notepad."""

    APP_NAME = "notepad"
    PROCESS_NAMES = ["notepad.exe", "notepad"]
    EXE_HINTS = ["notepad", "notepad.exe"]

    def open_file(self, path: str) -> Dict:
        return self.run_command(["notepad.exe", path])

    def new_note(self, text: str = "") -> Dict:
        opened = self.open()
        if opened.get("error"):
            return opened
        if text:
            time.sleep(0.8)
            self.type_text(text)
        return {"success": True}

    def write_text(self, path: str, text: str) -> Dict:
        try:
            Path(path).write_text(text, encoding="utf-8")
            return {"success": True, "path": path}
        except Exception as e:
            return {"error": str(e)}

    def append_text(self, path: str, text: str) -> Dict:
        try:
            with open(path, "a", encoding="utf-8") as f:
                f.write(text)
            return {"success": True, "path": path}
        except Exception as e:
            return {"error": str(e)}
