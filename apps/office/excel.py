"""Microsoft Excel automation (GUI-level; see files/office/office.py for
headless .xlsx creation/editing via openpyxl)."""

import time
from typing import Dict

from apps.base_app import BaseApp


class ExcelApp(BaseApp):
    """Open, edit, save, and print .xlsx files via Microsoft Excel."""

    APP_NAME = "excel"
    PROCESS_NAMES = ["excel.exe", "excel"]
    EXE_HINTS = ["excel", "excel.exe"]

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

    def new_workbook(self) -> Dict:
        return self.open()

    def save(self) -> Dict:
        focused = self.focus()
        if focused.get("error"):
            return focused
        time.sleep(0.3)
        return self.press_key("ctrl+s")

    def new_sheet(self) -> Dict:
        focused = self.focus()
        if focused.get("error"):
            return focused
        time.sleep(0.3)
        return self.press_key("shift+f11")

    def print_workbook(self) -> Dict:
        focused = self.focus()
        if focused.get("error"):
            return focused
        time.sleep(0.3)
        return self.press_key("ctrl+p")

    def close_workbook(self) -> Dict:
        focused = self.focus()
        if focused.get("error"):
            return focused
        time.sleep(0.3)
        return self.press_key("ctrl+w")
