"""
WhatsApp skill
==============
Send messages/media via the official WhatsApp Business Cloud API (Meta).
Needs a Meta developer app with WhatsApp product added.

Setup (.env):
    WHATSAPP_ACCESS_TOKEN   - permanent or temporary access token
    WHATSAPP_PHONE_NUMBER_ID - the sender number's phone_number_id
    WHATSAPP_API_VERSION    - defaults to v20.0
"""

import os
from typing import Dict, List, Optional

import requests


class WhatsAppClient:
    """Wrapper around the WhatsApp Business Cloud API."""

    def __init__(
        self,
        access_token: Optional[str] = None,
        phone_number_id: Optional[str] = None,
        api_version: Optional[str] = None,
    ):
        self.access_token = access_token or os.getenv("WHATSAPP_ACCESS_TOKEN")
        self.phone_number_id = phone_number_id or os.getenv("WHATSAPP_PHONE_NUMBER_ID")
        self.api_version = api_version or os.getenv("WHATSAPP_API_VERSION", "v20.0")

    def is_configured(self) -> bool:
        return bool(self.access_token and self.phone_number_id)

    def _url(self) -> str:
        return f"https://graph.facebook.com/{self.api_version}/{self.phone_number_id}/messages"

    def _headers(self) -> Dict:
        return {"Authorization": f"Bearer {self.access_token}", "Content-Type": "application/json"}

    def send_message(self, to: str, message: str) -> Dict:
        """to: recipient phone number in international format, no '+' (e.g. '919876543210')."""
        if not self.is_configured():
            return {
                "success": False,
                "error": "WhatsApp not configured. Set WHATSAPP_ACCESS_TOKEN and WHATSAPP_PHONE_NUMBER_ID.",
            }
        try:
            payload = {
                "messaging_product": "whatsapp",
                "to": to,
                "type": "text",
                "text": {"body": message},
            }
            resp = requests.post(self._url(), headers=self._headers(), json=payload, timeout=15)
            resp.raise_for_status()
            data = resp.json()
            return {"success": True, "to": to, "message_id": data.get("messages", [{}])[0].get("id")}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def send_template(
        self, to: str, template_name: str, language_code: str = "en_US", params: Optional[List[str]] = None
    ) -> Dict:
        """Send a pre-approved WhatsApp template message (required for the first
        message in a 24h window, or for marketing/notification bulk sends)."""
        if not self.is_configured():
            return {"success": False, "error": "WhatsApp not configured."}
        try:
            components = []
            if params:
                components.append({"type": "body", "parameters": [{"type": "text", "text": p} for p in params]})
            payload = {
                "messaging_product": "whatsapp",
                "to": to,
                "type": "template",
                "template": {"name": template_name, "language": {"code": language_code}, "components": components},
            }
            resp = requests.post(self._url(), headers=self._headers(), json=payload, timeout=15)
            resp.raise_for_status()
            return {"success": True, "to": to, "template": template_name}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def send_media(self, to: str, media_url: str, media_type: str = "image", caption: str = "") -> Dict:
        """media_type: image | document | video | audio"""
        if not self.is_configured():
            return {"success": False, "error": "WhatsApp not configured."}
        try:
            payload = {
                "messaging_product": "whatsapp",
                "to": to,
                "type": media_type,
                media_type: {"link": media_url, **({"caption": caption} if caption else {})},
            }
            resp = requests.post(self._url(), headers=self._headers(), json=payload, timeout=15)
            resp.raise_for_status()
            return {"success": True, "to": to, "media_type": media_type}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def mark_as_read(self, message_id: str) -> Dict:
        if not self.is_configured():
            return {"success": False, "error": "WhatsApp not configured."}
        try:
            payload = {"messaging_product": "whatsapp", "status": "read", "message_id": message_id}
            resp = requests.post(self._url(), headers=self._headers(), json=payload, timeout=15)
            resp.raise_for_status()
            return {"success": True, "message_id": message_id}
        except Exception as e:
            return {"success": False, "error": str(e)}
