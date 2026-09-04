"""Microsoft PowerPoint automation (GUI-level; see files/office/office.py
for headless .pptx creation via python-pptx)."""

import time
from typing import Dict

from apps.base_app import BaseApp


class PowerPointApp(BaseApp):
    """Open, present, save, and print .pptx files via PowerPoint."""

    APP_NAME = "powerpoint"
    PROCESS_NAMES = ["powerpnt.exe", "powerpnt"]
    EXE_HINTS = ["powerpnt", "powerpnt.exe"]

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

    def new_presentation(self) -> Dict:
        return self.open()

    def start_slideshow(self) -> Dict:
        focused = self.focus()
        if focused.get("error"):
            return focused
        time.sleep(0.3)
        return self.press_key("f5")

    def end_slideshow(self) -> Dict:
        return self.press_key("esc")

    def next_slide(self) -> Dict:
        return self.press_key("right")

    def previous_slide(self) -> Dict:
        return self.press_key("left")

    def save(self) -> Dict:
        focused = self.focus()
        if focused.get("error"):
            return focused
        time.sleep(0.3)
        return self.press_key("ctrl+s")
