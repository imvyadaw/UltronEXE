"""Epic Games Launcher automation (com.epicgames.launcher:// protocol scheme)."""

import webbrowser
from typing import Dict

from apps.base_app import BaseApp


class EpicGamesApp(BaseApp):
    """Open the Epic Games Launcher and launch games by their app name."""

    APP_NAME = "epic games launcher"
    PROCESS_NAMES = ["epicgameslauncher.exe", "epicgameslauncher"]
    EXE_HINTS = ["epicgameslauncher", "epicgameslauncher.exe"]

    def launch_game(self, app_name: str, silent: bool = True) -> Dict:
        try:
            silent_flag = "true" if silent else "false"
            webbrowser.open(f"com.epicgames.launcher://apps/{app_name}?action=launch&silent={silent_flag}")
            return {"success": True, "app_name": app_name}
        except Exception as e:
            return {"error": str(e)}

    def open_store(self) -> Dict:
        try:
            webbrowser.open("com.epicgames.launcher://store")
            return {"success": True}
        except Exception as e:
            return {"error": str(e)}
