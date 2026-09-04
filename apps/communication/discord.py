"""
Discord automation
=====================
Uses Discord's discord:// deep-link scheme to jump directly to a
server/channel by ID.
"""

import webbrowser
from typing import Dict

from apps.base_app import BaseApp


class DiscordApp(BaseApp):
    """Open servers/channels and send messages via Discord Desktop."""

    APP_NAME = "discord"
    PROCESS_NAMES = ["discord.exe", "discord"]
    EXE_HINTS = ["discord", "discord.exe"]

    def open_channel(self, server_id: str, channel_id: str) -> Dict:
        try:
            webbrowser.open(f"discord://discord.com/channels/{server_id}/{channel_id}")
            return {"success": True, "server_id": server_id, "channel_id": channel_id}
        except Exception as e:
            return {"error": str(e)}

    def open_dm(self, channel_id: str) -> Dict:
        try:
            webbrowser.open(f"discord://discord.com/channels/@me/{channel_id}")
            return {"success": True, "channel_id": channel_id}
        except Exception as e:
            return {"error": str(e)}

    def send_message_to_open_channel(self, message: str) -> Dict:
        """Sends into whichever channel is currently focused in Discord -
        use open_channel()/open_dm() first if you have IDs."""
        return self.type_and_send(message)
