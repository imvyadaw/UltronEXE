"""Adobe Photoshop automation (GUI-level: open/save/export via hotkeys)."""

import time
from typing import Dict

from apps.base_app import BaseApp


class PhotoshopApp(BaseApp):
    """Open image files and drive save/export in Photoshop."""

    APP_NAME = "photoshop"
    PROCESS_NAMES = ["photoshop.exe", "photoshop"]
    EXE_HINTS = ["photoshop", "photoshop.exe"]

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

    def save(self) -> Dict:
        focused = self.focus()
        if focused.get("error"):
            return focused
        time.sleep(0.3)
        return self.press_key("ctrl+s")

    def export_for_web(self) -> Dict:
        focused = self.focus()
        if focused.get("error"):
            return focused
        time.sleep(0.3)
        return self.press_key("ctrl+alt+shift+s")

    def undo(self) -> Dict:
        return self.press_key("ctrl+z")
