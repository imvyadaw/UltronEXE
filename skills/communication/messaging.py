"""
Messaging skill (Phase 4 facade)
=================================
One "send(channel=...)" entry point across SMS (Twilio), Telegram, and
WhatsApp Business (skills/communication/sms.py, telegram.py, whatsapp.py),
instead of three separate provider-specific tool calls.
"""

from typing import Dict, Optional

from skills.base_skill import BaseSkill
from skills.communication.sms import SMSClient
from skills.communication.telegram import TelegramClient
from skills.communication.whatsapp import WhatsAppClient


class MessagingHandler(BaseSkill):
    """Unified send/status interface across SMS, Telegram, and WhatsApp."""

    name = "messaging"
    description = "Send SMS, Telegram, or WhatsApp messages and media through one unified interface."
    category = "communication"

    def __init__(self):
        self._sms = SMSClient()
        self._telegram = TelegramClient()
        self._whatsapp = WhatsAppClient()
        super().__init__()

    def _client(self, channel: str):
        channel = (channel or "").lower()
        if channel == "sms":
            return self._sms
        if channel == "telegram":
            return self._telegram
        if channel == "whatsapp":
            return self._whatsapp
        raise ValueError(f"Unknown channel '{channel}' - use 'sms', 'telegram', or 'whatsapp'.")

    def send_message(self, channel: str, to: Optional[str] = None, message: str = "", **kwargs) -> Dict:
        client = self._client(channel)
        if channel == "sms":
            return client.send_sms(to=to, message=message)
        if channel == "telegram":
            return client.send_message(message=message, chat_id=to, **kwargs)
        return client.send_message(to=to, message=message)

    def send_media(
        self, channel: str, to: Optional[str] = None, media_url: str = "", caption: str = "", **kwargs
    ) -> Dict:
        client = self._client(channel)
        if channel == "telegram":
            return client.send_photo(photo_url=media_url, caption=caption, chat_id=to)
        if channel == "whatsapp":
            return client.send_media(to=to, media_url=media_url, caption=caption, **kwargs)
        return {"success": False, "error": "send_media is only available for 'telegram' and 'whatsapp'."}

    def status(self, channel: str, message_id: Optional[str] = None) -> Dict:
        client = self._client(channel)
        if channel == "sms":
            return client.get_message_status(message_id)
        return {"success": False, "error": f"status lookups aren't supported for '{channel}'."}

    def register_actions(self) -> None:
        s, t = self._sms, self._telegram
        self._actions = {
            "send": self.send_message,
            "send_media": self.send_media,
            "status": self.status,
            "list_recent_sms": s.list_recent_messages,
            "get_telegram_updates": t.get_updates,
            "get_telegram_chat_id": t.get_chat_id_from_updates,
        }

    def health_check(self) -> Dict:
        return {
            "success": True,
            "skill": self.name,
            "sms_configured": self._sms.is_configured(),
            "telegram_configured": self._telegram.is_configured(),
            "whatsapp_configured": self._whatsapp.is_configured(),
        }
