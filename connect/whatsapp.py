"""
WhatsApp (CONNECT)
===================
Sends via the WhatsApp Business Cloud API (Meta's Graph API) - a real
HTTP call to a phone number, no WhatsApp Desktop window required at
all. This is a different backend from apps/communication/whatsapp.py
(Phase 6), which drives the installed WhatsApp Desktop app through UI
automation, and from ACTIONS/send_message.py (this phase), which is
the coordinate-based fallback for apps with no dedicated class. Three
paths to the same outcome, in order of preference: apps/communication/
whatsapp.py for a normal chat with the app already set up, this module
when no desktop client is available at all (a server, a headless box),
ACTIONS/send_message.py as the last resort.

Requires a Meta Business app's WHATSAPP_ACCESS_TOKEN and
WHATSAPP_PHONE_NUMBER_ID (the sender's registered number ID, not the
recipient's number) as environment variables - never hardcoded here.
Same empty/failure-safe contract as PHASE_18_5_SEARCH_ENGINE: no
`requests`, no configured credentials, or any request failure all
collapse to {"success": False, ...} rather than an exception.

send_message.py's text can be drafted by
PHASE_18_6_AI_AGENTS/AGENTS/writer.py and reviewed by that phase's
guard.py before it ever reaches this module - this module's own job
is only the send.
"""

import os
from typing import Dict, Optional

try:
    import requests

    _REQUESTS_AVAILABLE = True
except Exception:
    _REQUESTS_AVAILABLE = False

ACCESS_TOKEN_ENV = "WHATSAPP_ACCESS_TOKEN"
PHONE_NUMBER_ID_ENV = "WHATSAPP_PHONE_NUMBER_ID"
API_VERSION = "v19.0"
DEFAULT_TIMEOUT_SECONDS = 10


class WhatsAppConnect:
    """WhatsApp Business Cloud API sender. Use get_whatsapp()."""

    def is_available(self) -> bool:
        return (
            _REQUESTS_AVAILABLE and bool(os.environ.get(ACCESS_TOKEN_ENV)) and bool(os.environ.get(PHONE_NUMBER_ID_ENV))
        )

    def send_message(self, to: str, text: str) -> Dict:
        """Sends `text` to `to` (E.164 format, e.g. "+15551234567")
        via the Cloud API. Returns
        {"success": bool, "message_id": Optional[str], "error": Optional[str]}."""
        if not self.is_available():
            return {"success": False, "message_id": None, "error": "backend unavailable"}
        if not to or not text:
            return {"success": False, "message_id": None, "error": "to and text both required"}
        phone_number_id = os.environ[PHONE_NUMBER_ID_ENV]
        url = f"https://graph.facebook.com/{API_VERSION}/{phone_number_id}/messages"
        try:
            response = requests.post(
                url,
                headers={"Authorization": f"Bearer {os.environ[ACCESS_TOKEN_ENV]}"},
                json={
                    "messaging_product": "whatsapp",
                    "to": to,
                    "type": "text",
                    "text": {"body": text},
                },
                timeout=DEFAULT_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            data = response.json()
            message_id = (data.get("messages") or [{}])[0].get("id")
            return {"success": True, "message_id": message_id, "error": None}
        except Exception as exc:
            return {"success": False, "message_id": None, "error": str(exc)}


_whatsapp: Optional[WhatsAppConnect] = None


def get_whatsapp() -> WhatsAppConnect:
    global _whatsapp
    if _whatsapp is None:
        _whatsapp = WhatsAppConnect()
    return _whatsapp
