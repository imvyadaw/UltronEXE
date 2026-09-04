"""
Telegram automation
======================
Uses the tg:// protocol scheme (Telegram Desktop registers this on
install) to jump straight to a user/channel by username.
"""

import time
import webbrowser
from typing import Dict

from apps.base_app import BaseApp


class TelegramApp(BaseApp):
    """Open chats and send messages via Telegram Desktop."""

    APP_NAME = "telegram"
    PROCESS_NAMES = ["telegram.exe", "telegram"]
    EXE_HINTS = ["telegram", "telegram.exe"]

    def open_chat(self, username: str) -> Dict:
        try:
            webbrowser.open(f"tg://resolve?domain={username.lstrip('@')}")
            return {"success": True, "username": username}
        except Exception as e:
            return {"error": str(e)}

    def send_message(self, username: str, message: str, wait_seconds: float = 3.0) -> Dict:
        opened = self.open_chat(username)
        if opened.get("error"):
            return opened
        time.sleep(wait_seconds)
        return self.type_and_send(message, focus_first=False)
