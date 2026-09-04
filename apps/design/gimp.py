"""GIMP automation (GUI-level: open/save/export via hotkeys, plus
Script-Fu batch mode for headless operations)."""

import time
from typing import Dict, Optional

from apps.base_app import BaseApp


class GimpApp(BaseApp):
    """Open image files and drive save/export in GIMP."""

    APP_NAME = "gimp"
    PROCESS_NAMES = ["gimp.exe", "gimp-2", "gimp"]
    EXE_HINTS = ["gimp", "gimp.exe", "gimp-2.10"]

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

    def export_as(self, script_fu_export_path: Optional[str] = None) -> Dict:
        """Opens the Export As dialog (Shift+Ctrl+E); pass a path via a
        follow-up type_text() + Enter, since the dialog needs to be visible
        first."""
        focused = self.focus()
        if focused.get("error"):
            return focused
        time.sleep(0.3)
        result = self.press_key("shift+ctrl+e")
        if script_fu_export_path:
            time.sleep(0.5)
            self.type_text(script_fu_export_path)
        return result

    def save_xcf(self) -> Dict:
        focused = self.focus()
        if focused.get("error"):
            return focused
        time.sleep(0.3)
        return self.press_key("ctrl+s")

    def run_batch_script(self, script_fu_command: str) -> Dict:
        """Runs GIMP in headless batch mode with a Script-Fu command -
        the real way to automate GIMP without touching the GUI at all."""
        exe = self.resolve_executable()
        if not exe:
            return {"error": "gimp executable not found"}
        return self.run_and_capture([exe, "-i", "-b", script_fu_command, "-b", "(gimp-quit 0)"])
