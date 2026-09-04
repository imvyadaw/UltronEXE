"""Figma automation (web/desktop hybrid - opens the site/a file URL)."""

import webbrowser
from typing import Dict

from apps.base_app import BaseApp


class FigmaApp(BaseApp):
    """Open Figma and jump to a specific file."""

    APP_NAME = "figma"
    PROCESS_NAMES = ["figma.exe", "figma"]
    EXE_HINTS = ["figma", "figma.exe"]

    def open_web(self) -> Dict:
        try:
            webbrowser.open("https://www.figma.com/files/recent")
            return {"success": True}
        except Exception as e:
            return {"error": str(e)}

    def open_file(self, file_url: str) -> Dict:
        try:
            webbrowser.open(file_url)
            return {"success": True, "file_url": file_url}
        except Exception as e:
            return {"error": str(e)}
