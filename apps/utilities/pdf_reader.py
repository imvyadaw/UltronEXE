"""PDF reader automation (opens files via the OS default handler; see
files/pdf/pdf.py for actual PDF content extraction/manipulation)."""

import os
from typing import Dict, Optional

from apps.base_app import BaseApp


class PDFReaderApp(BaseApp):
    """Open PDF files, optionally jumped to a specific page."""

    APP_NAME = "pdf reader"
    PROCESS_NAMES = ["acrord32.exe", "acrobat.exe", "sumatrapdf.exe"]
    EXE_HINTS = ["sumatrapdf", "sumatrapdf.exe", "acrord32.exe"]

    def open_file(self, path: str, page: Optional[int] = None) -> Dict:
        exe = self.resolve_executable()
        try:
            if exe and page:
                if "sumatra" in exe.lower():
                    return self.run_command([exe, "-page", str(page), path])
                if "acro" in exe.lower():
                    return self.run_command([exe, "/A", f"page={page}", path])
            os.startfile(path)
            return {"success": True, "path": path}
        except Exception as e:
            return {"error": str(e)}
