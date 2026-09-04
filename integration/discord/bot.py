"""
Discord integration
====================
Send messages, read channel history, manage a Discord server via the
Discord REST API (bot token) - raw requests, no discord.py dependency,
since Ultron needs simple request/response calls rather than a persistent
gateway connection.

Setup (.env): DISCORD_BOT_TOKEN from https://discord.com/developers/applications
(needs the "bot" scope + Send Messages / Read Message History permissions,
and must be invited to the target server).
"""

import os
from typing import Dict, Optional

import requests

BASE_URL = "https://discord.com/api/v10"


class DiscordClient:
    """Wrapper around the Discord REST API for bot actions."""

    def __init__(self, bot_token: Optional[str] = None):
        self.bot_token = bot_token or os.getenv("DISCORD_BOT_TOKEN")

    def is_configured(self) -> bool:
        return bool(self.bot_token)

    def _headers(self) -> Dict:
        return {"Authorization": f"Bot {self.bot_token}", "Content-Type": "application/json"}

    def send_message(self, channel_id: str, message: str) -> Dict:
        if not self.is_configured():
            return {"success": False, "error": "DISCORD_BOT_TOKEN not set in .env"}
        try:
            resp = requests.post(
                f"{BASE_URL}/channels/{channel_id}/messages",
                headers=self._headers(),
                json={"content": message},
                timeout=15,
            )
            resp.raise_for_status()
            data = resp.json()
            return {"success": True, "channel_id": channel_id, "message_id": data.get("id")}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def read_channel_history(self, channel_id: str, limit: int = 20) -> Dict:
        if not self.is_configured():
            return {"success": False, "error": "DISCORD_BOT_TOKEN not set."}
        try:
            resp = requests.get(
                f"{BASE_URL}/channels/{channel_id}/messages",
                headers=self._headers(),
                params={"limit": limit},
                timeout=15,
            )
            resp.raise_for_status()
            messages = [
                {
                    "author": m["author"]["username"],
                    "content": m["content"],
                    "timestamp": m["timestamp"],
                    "id": m["id"],
                }
                for m in resp.json()
            ]
            return {"success": True, "channel_id": channel_id, "count": len(messages), "messages": messages}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def list_channels(self, guild_id: str) -> Dict:
        if not self.is_configured():
            return {"success": False, "error": "DISCORD_BOT_TOKEN not set."}
        try:
            resp = requests.get(f"{BASE_URL}/guilds/{guild_id}/channels", headers=self._headers(), timeout=15)
            resp.raise_for_status()
            channels = [{"id": c["id"], "name": c["name"], "type": c["type"]} for c in resp.json()]
            return {"success": True, "count": len(channels), "channels": channels}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def add_reaction(self, channel_id: str, message_id: str, emoji: str = "\U0001f44d") -> Dict:
        """emoji: unicode emoji character, or 'name:id' for custom server emoji."""
        if not self.is_configured():
            return {"success": False, "error": "DISCORD_BOT_TOKEN not set."}
        try:
            from urllib.parse import quote

            url = f"{BASE_URL}/channels/{channel_id}/messages/{message_id}/reactions/{quote(emoji)}/@me"
            resp = requests.put(url, headers=self._headers(), timeout=15)
            resp.raise_for_status()
            return {"success": True, "channel_id": channel_id, "message_id": message_id}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def delete_message(self, channel_id: str, message_id: str) -> Dict:
        if not self.is_configured():
            return {"success": False, "error": "DISCORD_BOT_TOKEN not set."}
        try:
            resp = requests.delete(
                f"{BASE_URL}/channels/{channel_id}/messages/{message_id}", headers=self._headers(), timeout=15
            )
            resp.raise_for_status()
            return {"success": True, "message_id": message_id}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def send_webhook_message(self, webhook_url: str, message: str, username: str = "Ultron") -> Dict:
        """Simplest way to post without a full bot invite - just a channel webhook URL."""
        try:
            resp = requests.post(webhook_url, json={"content": message, "username": username}, timeout=15)
            resp.raise_for_status()
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}
