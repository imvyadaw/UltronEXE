"""JetBrains PyCharm automation."""

from typing import Dict

from apps.base_app import BaseApp


class PyCharmApp(BaseApp):
    """Open projects/files in PyCharm."""

    APP_NAME = "pycharm"
    PROCESS_NAMES = ["pycharm64.exe", "pycharm.exe", "pycharm"]
    EXE_HINTS = ["pycharm64", "pycharm", "pycharm64.exe", "pycharm.exe"]

    def open_project(self, path: str) -> Dict:
        exe = self.resolve_executable()
        if exe:
            return self.run_command([exe, path])
        try:
            import os

            os.startfile(path)
            return {"success": True, "path": path}
        except Exception as e:
            return {"error": str(e)}
