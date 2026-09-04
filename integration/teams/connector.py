"""
Microsoft Teams integration
============================
Two supported paths, since they need very different setups:

1. Incoming Webhook (simplest - no Azure app needed): post a message card
   to a channel via a webhook URL configured in Teams
   (Channel -> Connectors -> Incoming Webhook).
2. Graph API (chat/channel messages, needs the same Azure AD app as
   skills/email/outlook.py, with ChannelMessage.Send / Chat.ReadWrite scopes).
"""

import os
from typing import Dict, Optional

import requests

try:
    import msal

    HAS_MSAL = True
except ImportError:
    HAS_MSAL = False

from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent
GRAPH_URL = "https://graph.microsoft.com/v1.0"
SCOPES = ["ChannelMessage.Send", "Chat.ReadWrite"]


class TeamsClient:
    """Wrapper supporting both webhook posting and Graph API messaging."""

    def __init__(
        self,
        webhook_url: Optional[str] = None,
        client_id: Optional[str] = None,
        tenant_id: Optional[str] = None,
        cache_path: Optional[str] = None,
    ):
        self.webhook_url = webhook_url or os.getenv("TEAMS_WEBHOOK_URL")
        self.client_id = client_id or os.getenv("OUTLOOK_CLIENT_ID")  # same Azure AD app is fine
        self.tenant_id = tenant_id or os.getenv("OUTLOOK_TENANT_ID", "common")
        self.cache_path = Path(
            cache_path or os.getenv("TEAMS_TOKEN_CACHE", BASE_DIR / "storage" / "cache" / "teams_token_cache.bin")
        )

    def is_webhook_configured(self) -> bool:
        return bool(self.webhook_url)

    def is_graph_configured(self) -> bool:
        return HAS_MSAL and bool(self.client_id)

    # -- simple path: webhook -------------------------------------------
    def send_webhook_message(self, title: str, message: str, webhook_url: Optional[str] = None) -> Dict:
        url = webhook_url or self.webhook_url
        if not url:
            return {"success": False, "error": "No Teams webhook URL configured (TEAMS_WEBHOOK_URL)."}
        try:
            card = {
                "@type": "MessageCard",
                "@context": "http://schema.org/extensions",
                "summary": title,
                "themeColor": "0076D7",
                "title": title,
                "text": message,
            }
            resp = requests.post(url, json=card, timeout=15)
            resp.raise_for_status()
            return {"success": True, "title": title}
        except Exception as e:
            return {"success": False, "error": str(e)}

    # -- full path: Graph API ---------------------------------------------
    def _get_token(self) -> str:
        if not HAS_MSAL:
            raise RuntimeError("Teams Graph support needs: pip install msal")
        if not self.client_id:
            raise RuntimeError("Set OUTLOOK_CLIENT_ID in .env (shared Azure AD app).")

        cache = msal.SerializableTokenCache()
        if self.cache_path.exists():
            cache.deserialize(self.cache_path.read_text())
        app = msal.PublicClientApplication(
            self.client_id, authority=f"https://login.microsoftonline.com/{self.tenant_id}", token_cache=cache
        )
        accounts = app.get_accounts()
        result = app.acquire_token_silent(SCOPES, account=accounts[0]) if accounts else None
        if not result:
            flow = app.initiate_device_flow(scopes=SCOPES)
            if "user_code" not in flow:
                raise RuntimeError(f"Device flow failed: {flow}")
            print(flow["message"])
            result = app.acquire_token_by_device_flow(flow)
        if "access_token" not in result:
            raise RuntimeError(f"Auth failed: {result.get('error_description', result)}")
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        self.cache_path.write_text(cache.serialize())
        return result["access_token"]

    def send_channel_message(self, team_id: str, channel_id: str, message: str) -> Dict:
        try:
            headers = {"Authorization": f"Bearer {self._get_token()}", "Content-Type": "application/json"}
            payload = {"body": {"content": message}}
            resp = requests.post(
                f"{GRAPH_URL}/teams/{team_id}/channels/{channel_id}/messages", headers=headers, json=payload, timeout=15
            )
            resp.raise_for_status()
            return {"success": True, "team_id": team_id, "channel_id": channel_id}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def list_teams(self) -> Dict:
        try:
            headers = {"Authorization": f"Bearer {self._get_token()}"}
            resp = requests.get(f"{GRAPH_URL}/me/joinedTeams", headers=headers, timeout=15)
            resp.raise_for_status()
            teams = [{"id": t["id"], "name": t["displayName"]} for t in resp.json().get("value", [])]
            return {"success": True, "count": len(teams), "teams": teams}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def list_channels(self, team_id: str) -> Dict:
        try:
            headers = {"Authorization": f"Bearer {self._get_token()}"}
            resp = requests.get(f"{GRAPH_URL}/teams/{team_id}/channels", headers=headers, timeout=15)
            resp.raise_for_status()
            channels = [{"id": c["id"], "name": c["displayName"]} for c in resp.json().get("value", [])]
            return {"success": True, "count": len(channels), "channels": channels}
        except Exception as e:
            return {"success": False, "error": str(e)}
