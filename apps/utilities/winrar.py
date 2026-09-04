"""
WinRAR automation
====================
Drives the real WinRAR.exe CLI switches when installed (needed for
.rar); falls back to Python's built-in zipfile/shutil for .zip so
compress/extract still work with nothing extra installed.
"""

import zipfile
from pathlib import Path
from typing import Dict, List

from apps.base_app import BaseApp


class WinRARApp(BaseApp):
    """Compress and extract archives via WinRAR (or zipfile fallback)."""

    APP_NAME = "winrar"
    PROCESS_NAMES = ["winrar.exe", "winrar"]
    EXE_HINTS = ["winrar", "winrar.exe", "rar", "rar.exe"]

    def extract(self, archive_path: str, destination: str) -> Dict:
        exe = self.resolve_executable()
        try:
            if exe and archive_path.lower().endswith(".rar"):
                return self.run_and_capture([exe, "x", "-y", archive_path, destination + "\\"], timeout=120.0)
            Path(destination).mkdir(parents=True, exist_ok=True)
            with zipfile.ZipFile(archive_path) as zf:
                zf.extractall(destination)
            return {"success": True, "extracted_to": destination}
        except Exception as e:
            return {"error": str(e)}

    def compress(self, files: List[str], archive_path: str) -> Dict:
        exe = self.resolve_executable()
        try:
            if exe and archive_path.lower().endswith(".rar"):
                return self.run_and_capture([exe, "a", "-y", archive_path, *files], timeout=120.0)
            if not archive_path.lower().endswith(".zip"):
                archive_path += ".zip"
            with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED) as zf:
                for f in files:
                    zf.write(f, Path(f).name)
            return {"success": True, "archive_path": archive_path}
        except Exception as e:
            return {"error": str(e)}

    def list_contents(self, archive_path: str) -> Dict:
        try:
            if archive_path.lower().endswith(".zip"):
                with zipfile.ZipFile(archive_path) as zf:
                    return {"success": True, "files": zf.namelist()}
            exe = self.resolve_executable()
            if exe:
                return self.run_and_capture([exe, "l", archive_path])
            return {"error": "Only .zip listing is supported without WinRAR installed"}
        except Exception as e:
            return {"error": str(e)}
