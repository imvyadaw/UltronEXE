"""
SMS skill
=========
Send/receive SMS via Twilio's REST API (raw requests, no twilio SDK
dependency needed - keeps requirements.txt lighter).

Setup (.env):
    TWILIO_ACCOUNT_SID
    TWILIO_AUTH_TOKEN
    TWILIO_FROM_NUMBER   - your Twilio number, e.g. '+15551234567'
"""

import os
from typing import Dict, Optional

import requests
from requests.auth import HTTPBasicAuth


class SMSClient:
    """Wrapper around the Twilio Messages REST API."""

    def __init__(
        self, account_sid: Optional[str] = None, auth_token: Optional[str] = None, from_number: Optional[str] = None
    ):
        self.account_sid = account_sid or os.getenv("TWILIO_ACCOUNT_SID")
        self.auth_token = auth_token or os.getenv("TWILIO_AUTH_TOKEN")
        self.from_number = from_number or os.getenv("TWILIO_FROM_NUMBER")

    def is_configured(self) -> bool:
        return bool(self.account_sid and self.auth_token and self.from_number)

    def _base_url(self) -> str:
        return f"https://api.twilio.com/2010-04-01/Accounts/{self.account_sid}/Messages.json"

    def send_sms(self, to: str, message: str) -> Dict:
        """to: E.164 format, e.g. '+919876543210'."""
        if not self.is_configured():
            return {
                "success": False,
                "error": "SMS not configured. Set TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_FROM_NUMBER.",
            }
        try:
            resp = requests.post(
                self._base_url(),
                data={"To": to, "From": self.from_number, "Body": message},
                auth=HTTPBasicAuth(self.account_sid, self.auth_token),
                timeout=15,
            )
            resp.raise_for_status()
            data = resp.json()
            return {"success": True, "sid": data.get("sid"), "to": to, "status": data.get("status")}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_message_status(self, message_sid: str) -> Dict:
        if not self.is_configured():
            return {"success": False, "error": "SMS not configured."}
        try:
            resp = requests.get(
                f"https://api.twilio.com/2010-04-01/Accounts/{self.account_sid}/Messages/{message_sid}.json",
                auth=HTTPBasicAuth(self.account_sid, self.auth_token),
                timeout=15,
            )
            resp.raise_for_status()
            data = resp.json()
            return {
                "success": True,
                "sid": message_sid,
                "status": data.get("status"),
                "error_message": data.get("error_message"),
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    def list_recent_messages(self, limit: int = 10) -> Dict:
        if not self.is_configured():
            return {"success": False, "error": "SMS not configured."}
        try:
            resp = requests.get(
                self._base_url(),
                params={"PageSize": limit},
                auth=HTTPBasicAuth(self.account_sid, self.auth_token),
                timeout=15,
            )
            resp.raise_for_status()
            messages = resp.json().get("messages", [])
            summary = [
                {
                    "sid": m["sid"],
                    "to": m["to"],
                    "from": m["from"],
                    "body": m["body"],
                    "status": m["status"],
                    "date_sent": m.get("date_sent"),
                }
                for m in messages
            ]
            return {"success": True, "count": len(summary), "messages": summary}
        except Exception as e:
            return {"success": False, "error": str(e)}
