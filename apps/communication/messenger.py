"""Facebook Messenger automation (m.me web deep link)."""

import time
import webbrowser
from typing import Dict

from apps.base_app import BaseApp


class MessengerApp(BaseApp):
    """Open chats via m.me and send messages in Messenger (web/desktop)."""

    APP_NAME = "messenger"
    PROCESS_NAMES = ["messenger.exe", "messenger"]
    EXE_HINTS = ["messenger", "messenger.exe"]

    def open_chat(self, username: str) -> Dict:
        try:
            webbrowser.open(f"https://m.me/{username.lstrip('@')}")
            return {"success": True, "username": username}
        except Exception as e:
            return {"error": str(e)}

    def send_message(self, username: str, message: str, wait_seconds: float = 5.0) -> Dict:
        opened = self.open_chat(username)
        if opened.get("error"):
            return opened
        time.sleep(wait_seconds)
        return self.type_and_send(message, focus_first=False)
