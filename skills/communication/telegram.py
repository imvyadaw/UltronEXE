"""
Telegram skill
==============
Lightweight outbound-messaging wrapper around the Telegram Bot API
(send_message/send_photo/send_document/get updates), for when Ultron needs
to *push* a message/notification/report to a chat.

This is distinct from plugins/installed/telegram/telegram_bot.py, which
runs a persistent bot Application so a user can *control Ultron from*
Telegram. Use that for two-way remote control; use this module for simple
one-off outbound sends (alerts, reminders, reports) from any other skill.

Setup (.env): TELEGRAM_BOT_TOKEN (same token as the existing bot plugin),
and TELEGRAM_CHAT_ID for a default recipient if you always message the
same chat.
"""

import os
from typing import Dict, Optional

import requests

from config import TELEGRAM_BOT_TOKEN


class TelegramClient:
    """Simple REST wrapper around the Telegram Bot API for outbound messages."""

    def __init__(self, bot_token: Optional[str] = None, default_chat_id: Optional[str] = None):
        self.bot_token = bot_token or TELEGRAM_BOT_TOKEN
        self.default_chat_id = default_chat_id or os.getenv("TELEGRAM_CHAT_ID")

    def is_configured(self) -> bool:
        return bool(self.bot_token)

    def _url(self, method: str) -> str:
        return f"https://api.telegram.org/bot{self.bot_token}/{method}"

    def send_message(self, message: str, chat_id: Optional[str] = None, markdown: bool = False) -> Dict:
        chat_id = chat_id or self.default_chat_id
        if not self.is_configured():
            return {"success": False, "error": "TELEGRAM_BOT_TOKEN not set in .env"}
        if not chat_id:
            return {"success": False, "error": "No chat_id given and no TELEGRAM_CHAT_ID default set."}
        try:
            payload = {"chat_id": chat_id, "text": message}
            if markdown:
                payload["parse_mode"] = "Markdown"
            resp = requests.post(self._url("sendMessage"), json=payload, timeout=15)
            resp.raise_for_status()
            return {"success": True, "chat_id": chat_id, "message_id": resp.json()["result"]["message_id"]}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def send_photo(self, photo_url: str, caption: str = "", chat_id: Optional[str] = None) -> Dict:
        chat_id = chat_id or self.default_chat_id
        if not self.is_configured() or not chat_id:
            return {"success": False, "error": "Telegram not configured (token/chat_id)."}
        try:
            payload = {"chat_id": chat_id, "photo": photo_url, "caption": caption}
            resp = requests.post(self._url("sendPhoto"), json=payload, timeout=15)
            resp.raise_for_status()
            return {"success": True, "chat_id": chat_id}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def send_document(self, document_url: str, caption: str = "", chat_id: Optional[str] = None) -> Dict:
        chat_id = chat_id or self.default_chat_id
        if not self.is_configured() or not chat_id:
            return {"success": False, "error": "Telegram not configured (token/chat_id)."}
        try:
            payload = {"chat_id": chat_id, "document": document_url, "caption": caption}
            resp = requests.post(self._url("sendDocument"), json=payload, timeout=15)
            resp.raise_for_status()
            return {"success": True, "chat_id": chat_id}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_updates(self, offset: Optional[int] = None, limit: int = 10) -> Dict:
        """Poll for incoming messages (long-polling alternative to running the full bot)."""
        if not self.is_configured():
            return {"success": False, "error": "TELEGRAM_BOT_TOKEN not set."}
        try:
            params = {"limit": limit}
            if offset:
                params["offset"] = offset
            resp = requests.get(self._url("getUpdates"), params=params, timeout=15)
            resp.raise_for_status()
            updates = resp.json().get("result", [])
            return {"success": True, "count": len(updates), "updates": updates}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_chat_id_from_updates(self) -> Dict:
        """Helper for first-time setup: message the bot once, then call this to
        discover your chat_id for TELEGRAM_CHAT_ID in .env."""
        result = self.get_updates(limit=5)
        if not result["success"]:
            return result
        chat_ids = {u["message"]["chat"]["id"] for u in result["updates"] if "message" in u}
        return {"success": True, "chat_ids": list(chat_ids)}
