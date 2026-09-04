"""Microsoft Access automation."""

from typing import Dict

from apps.base_app import BaseApp


class AccessApp(BaseApp):
    """Open and create Access .accdb databases."""

    APP_NAME = "access"
    PROCESS_NAMES = ["msaccess.exe", "msaccess"]
    EXE_HINTS = ["msaccess", "msaccess.exe"]

    def open_database(self, path: str) -> Dict:
        exe = self.resolve_executable()
        if exe:
            return self.run_command([exe, path])
        try:
            import os

            os.startfile(path)
            return {"success": True, "path": path}
        except Exception as e:
            return {"error": str(e)}

    def new_database(self) -> Dict:
        return self.open()
