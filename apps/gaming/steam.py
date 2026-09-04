"""Steam automation (steam:// protocol scheme)."""

import webbrowser
from typing import Dict

from apps.base_app import BaseApp


class SteamApp(BaseApp):
    """Open Steam, launch games by App ID, and jump to the store/library."""

    APP_NAME = "steam"
    PROCESS_NAMES = ["steam.exe", "steam"]
    EXE_HINTS = ["steam", "steam.exe"]

    def launch_game(self, app_id: str) -> Dict:
        try:
            webbrowser.open(f"steam://rungameid/{app_id}")
            return {"success": True, "app_id": app_id}
        except Exception as e:
            return {"error": str(e)}

    def open_store_page(self, app_id: str) -> Dict:
        try:
            webbrowser.open(f"steam://store/{app_id}")
            return {"success": True, "app_id": app_id}
        except Exception as e:
            return {"error": str(e)}

    def open_library(self) -> Dict:
        try:
            webbrowser.open("steam://open/games")
            return {"success": True}
        except Exception as e:
            return {"error": str(e)}

    def open_friends(self) -> Dict:
        try:
            webbrowser.open("steam://open/friends")
            return {"success": True}
        except Exception as e:
            return {"error": str(e)}
