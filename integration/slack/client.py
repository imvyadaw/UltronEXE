"""
Slack integration
==================
Send messages, read channel history, manage reactions and uploads via the
Slack Web API (raw requests - avoids adding the slack_sdk dependency).

Setup (.env): SLACK_BOT_TOKEN (starts with 'xoxb-') from a Slack app with
scopes: chat:write, channels:history, channels:read, files:write, reactions:write.
"""

import os
from typing import Dict, Optional

import requests

BASE_URL = "https://slack.com/api"


class SlackClient:
    """Wrapper around the Slack Web API."""

    def __init__(self, bot_token: Optional[str] = None):
        self.bot_token = bot_token or os.getenv("SLACK_BOT_TOKEN")

    def is_configured(self) -> bool:
        return bool(self.bot_token)

    def _headers(self) -> Dict:
        return {"Authorization": f"Bearer {self.bot_token}", "Content-Type": "application/json; charset=utf-8"}

    def _call(self, method: str, payload: Dict) -> Dict:
        if not self.is_configured():
            return {"success": False, "error": "SLACK_BOT_TOKEN not set in .env"}
        try:
            resp = requests.post(f"{BASE_URL}/{method}", headers=self._headers(), json=payload, timeout=15)
            resp.raise_for_status()
            data = resp.json()
            if not data.get("ok"):
                return {"success": False, "error": data.get("error", "unknown Slack API error")}
            return {"success": True, **data}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def send_message(self, channel: str, text: str, thread_ts: Optional[str] = None) -> Dict:
        """channel: channel ID (e.g. 'C0123456') or name (e.g. '#general')."""
        payload = {"channel": channel, "text": text}
        if thread_ts:
            payload["thread_ts"] = thread_ts
        result = self._call("chat.postMessage", payload)
        if result.get("success"):
            return {"success": True, "channel": channel, "ts": result.get("ts")}
        return result

    def read_channel_history(self, channel: str, limit: int = 20) -> Dict:
        result = self._call("conversations.history", {"channel": channel, "limit": limit})
        if not result.get("success"):
            return result
        messages = [
            {"user": m.get("user"), "text": m.get("text"), "ts": m.get("ts")} for m in result.get("messages", [])
        ]
        return {"success": True, "channel": channel, "count": len(messages), "messages": messages}

    def list_channels(self, limit: int = 100) -> Dict:
        result = self._call("conversations.list", {"limit": limit})
        if not result.get("success"):
            return result
        channels = [
            {"id": c["id"], "name": c["name"], "is_private": c.get("is_private", False)}
            for c in result.get("channels", [])
        ]
        return {"success": True, "count": len(channels), "channels": channels}

    def add_reaction(self, channel: str, timestamp: str, emoji: str = "thumbsup") -> Dict:
        return self._call("reactions.add", {"channel": channel, "timestamp": timestamp, "name": emoji})

    def upload_file(self, channels: str, file_path: str, title: str = "", initial_comment: str = "") -> Dict:
        """Uses the newer files.getUploadURLExternal + files.completeUploadExternal flow."""
        if not self.is_configured():
            return {"success": False, "error": "SLACK_BOT_TOKEN not set."}
        try:
            import pathlib

            path = pathlib.Path(file_path)
            size = path.stat().st_size

            step1 = requests.post(
                f"{BASE_URL}/files.getUploadURLExternal",
                headers={"Authorization": f"Bearer {self.bot_token}"},
                params={"filename": path.name, "length": size},
                timeout=15,
            ).json()
            if not step1.get("ok"):
                return {"success": False, "error": step1.get("error")}

            with path.open("rb") as f:
                requests.post(step1["upload_url"], files={"file": f}, timeout=30)

            step3 = requests.post(
                f"{BASE_URL}/files.completeUploadExternal",
                headers=self._headers(),
                json={
                    "files": [{"id": step1["file_id"], "title": title or path.name}],
                    "channel_id": channels,
                    "initial_comment": initial_comment,
                },
                timeout=15,
            ).json()
            if not step3.get("ok"):
                return {"success": False, "error": step3.get("error")}
            return {"success": True, "file_id": step1["file_id"]}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def set_status(self, status_text: str, emoji: str = ":speech_balloon:") -> Dict:
        return self._call("users.profile.set", {"profile": {"status_text": status_text, "status_emoji": emoji}})
