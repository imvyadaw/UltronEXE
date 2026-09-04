"""Skype automation (skype: protocol scheme for chat/call)."""

import webbrowser
from typing import Dict

from apps.base_app import BaseApp


class SkypeApp(BaseApp):
    """Open chats and place calls via Skype's skype: protocol handler."""

    APP_NAME = "skype"
    PROCESS_NAMES = ["skype.exe", "skype"]
    EXE_HINTS = ["skype", "skype.exe"]

    def open_chat(self, contact: str) -> Dict:
        try:
            webbrowser.open(f"skype:{contact}?chat")
            return {"success": True, "contact": contact}
        except Exception as e:
            return {"error": str(e)}

    def call(self, contact: str, video: bool = False) -> Dict:
        try:
            action = "videocall" if video else "call"
            webbrowser.open(f"skype:{contact}?{action}")
            return {"success": True, "contact": contact, "video": video}
        except Exception as e:
            return {"error": str(e)}

    def send_message_to_open_chat(self, message: str) -> Dict:
        return self.type_and_send(message)
