"""Xbox app (Windows) automation."""

import webbrowser
from typing import Dict

from apps.base_app import BaseApp


class XboxApp(BaseApp):
    """Open the Xbox app and jump to the game bar / social panel."""

    APP_NAME = "xbox"
    PROCESS_NAMES = ["xboxapp.exe", "gamebar.exe"]
    EXE_HINTS = []

    def open_app(self) -> Dict:
        try:
            webbrowser.open("xbox:")
            return {"success": True}
        except Exception as e:
            return {"error": str(e)}

    def open_game_bar(self) -> Dict:
        """Windows key + G opens the Xbox Game Bar overlay."""
        return self.press_key("win+g")

    def take_game_clip(self) -> Dict:
        """Windows key + Alt + G records the last N seconds via Game Bar."""
        return self.press_key("win+alt+g")

    def screenshot(self) -> Dict:
        """Windows key + Alt + PrtScn takes a Game Bar screenshot."""
        return self.press_key("win+alt+printscreen")
