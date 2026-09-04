"""Canva automation (web app - opens the site/a design URL in the browser)."""

import webbrowser
from typing import Dict

from apps.base_app import BaseApp


class CanvaApp(BaseApp):
    """Open Canva and jump to a specific design."""

    APP_NAME = "canva"
    PROCESS_NAMES = []  # web app

    def open_web(self) -> Dict:
        try:
            webbrowser.open("https://www.canva.com")
            return {"success": True}
        except Exception as e:
            return {"error": str(e)}

    def open_design(self, design_url: str) -> Dict:
        try:
            webbrowser.open(design_url)
            return {"success": True, "design_url": design_url}
        except Exception as e:
            return {"error": str(e)}

    def new_design(self, design_type: str = "design") -> Dict:
        """design_type examples: 'presentation', 'instagram-post', 'poster'."""
        try:
            webbrowser.open(f"https://www.canva.com/{design_type}/create/")
            return {"success": True, "design_type": design_type}
        except Exception as e:
            return {"error": str(e)}
