"""Windows File Explorer automation."""

import os
import subprocess
from typing import Dict

from apps.base_app import BaseApp


class FileExplorerApp(BaseApp):
    """Open folders, select files, and jump to common shell locations."""

    APP_NAME = "file explorer"
    PROCESS_NAMES = ["explorer.exe"]
    EXE_HINTS = ["explorer", "explorer.exe"]

    def open_path(self, path: str) -> Dict:
        try:
            os.startfile(path)
            return {"success": True, "path": path}
        except Exception as e:
            return {"error": str(e)}

    def select_file(self, path: str) -> Dict:
        """Opens Explorer with the file highlighted (rather than opening it)."""
        try:
            subprocess.Popen(["explorer", "/select,", path])
            return {"success": True, "path": path}
        except Exception as e:
            return {"error": str(e)}

    def open_this_pc(self) -> Dict:
        return self.open_path("shell:MyComputerFolder")

    def open_downloads(self) -> Dict:
        return self.open_path(str(__import__("pathlib").Path.home() / "Downloads"))

    def open_recycle_bin(self) -> Dict:
        return self.open_path("shell:RecycleBinFolder")
