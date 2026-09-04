"""
Outlook skill
=============
Send, read, search Outlook / Microsoft 365 mail via Microsoft Graph API,
authenticated with MSAL (device-code flow so it works headless too).

Setup (one-time):
    1. Register an app in Azure AD (App registrations -> New registration).
       Add delegated Graph permissions: Mail.Read, Mail.Send, Mail.ReadWrite.
    2. Set OUTLOOK_CLIENT_ID (and OUTLOOK_TENANT_ID, default "common") in .env.
    3. First call prints a device-login code/URL; after signing in once,
       the token is cached at storage/cache/outlook_token_cache.bin.
"""

import os
from pathlib import Path
from typing import Dict, Optional

import requests

try:
    import msal

    HAS_MSAL = True
except ImportError:
    HAS_MSAL = False

BASE_DIR = Path(__file__).resolve().parent.parent.parent
GRAPH_URL = "https://graph.microsoft.com/v1.0"
SCOPES = ["Mail.Read", "Mail.Send", "Mail.ReadWrite"]


class OutlookClient:
    """Thin wrapper around Microsoft Graph mail endpoints."""

    def __init__(
        self, client_id: Optional[str] = None, tenant_id: Optional[str] = None, cache_path: Optional[str] = None
    ):
        self.client_id = client_id or os.getenv("OUTLOOK_CLIENT_ID")
        self.tenant_id = tenant_id or os.getenv("OUTLOOK_TENANT_ID", "common")
        self.cache_path = Path(
            cache_path or os.getenv("OUTLOOK_TOKEN_CACHE", BASE_DIR / "storage" / "cache" / "outlook_token_cache.bin")
        )
        self._token = None

    def is_configured(self) -> bool:
        return HAS_MSAL and bool(self.client_id)

    # -- auth -----------------------------------------------------------
    def _get_token(self) -> str:
        if not HAS_MSAL:
            raise RuntimeError("Outlook support needs: pip install msal")
        if not self.client_id:
            raise RuntimeError("Set OUTLOOK_CLIENT_ID in .env (Azure AD app registration).")

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
            print(flow["message"])  # user must visit URL + enter code
            result = app.acquire_token_by_device_flow(flow)

        if "access_token" not in result:
            raise RuntimeError(f"Auth failed: {result.get('error_description', result)}")

        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        self.cache_path.write_text(cache.serialize())
        return result["access_token"]

    def _headers(self) -> Dict:
        return {"Authorization": f"Bearer {self._get_token()}", "Content-Type": "application/json"}

    # -- send -------------------------------------------------------------
    def send_email(self, to: str, subject: str, body: str, cc: Optional[str] = None, html: bool = False) -> Dict:
        try:
            recipients = [{"emailAddress": {"address": addr.strip()}} for addr in to.split(",")]
            cc_recipients = [{"emailAddress": {"address": addr.strip()}} for addr in cc.split(",")] if cc else []
            payload = {
                "message": {
                    "subject": subject,
                    "body": {"contentType": "HTML" if html else "Text", "content": body},
                    "toRecipients": recipients,
                    "ccRecipients": cc_recipients,
                },
                "saveToSentItems": "true",
            }
            resp = requests.post(f"{GRAPH_URL}/me/sendMail", headers=self._headers(), json=payload, timeout=15)
            resp.raise_for_status()
            return {"success": True, "to": to, "subject": subject}
        except Exception as e:
            return {"success": False, "error": str(e)}

    # -- read / search ------------------------------------------------------
    def read_emails(self, max_results: int = 10, unread_only: bool = False) -> Dict:
        try:
            params = {"$top": max_results, "$orderby": "receivedDateTime desc"}
            if unread_only:
                params["$filter"] = "isRead eq false"
            resp = requests.get(
                f"{GRAPH_URL}/me/mailFolders/inbox/messages", headers=self._headers(), params=params, timeout=15
            )
            resp.raise_for_status()
            return {"success": True, "emails": [self._summarize(m) for m in resp.json().get("value", [])]}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def search_emails(self, query: str, max_results: int = 10) -> Dict:
        try:
            params = {"$search": f'"{query}"', "$top": max_results}
            headers = self._headers()
            headers["ConsistencyLevel"] = "eventual"
            resp = requests.get(f"{GRAPH_URL}/me/messages", headers=headers, params=params, timeout=15)
            resp.raise_for_status()
            return {"success": True, "emails": [self._summarize(m) for m in resp.json().get("value", [])]}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _summarize(self, m: Dict) -> Dict:
        return {
            "id": m.get("id"),
            "from": (m.get("from", {}).get("emailAddress", {}) or {}).get("address", ""),
            "subject": m.get("subject", ""),
            "date": m.get("receivedDateTime", ""),
            "snippet": m.get("bodyPreview", ""),
            "is_read": m.get("isRead", True),
        }

    # -- manage -------------------------------------------------------------
    def mark_as_read(self, message_id: str) -> Dict:
        try:
            resp = requests.patch(
                f"{GRAPH_URL}/me/messages/{message_id}", headers=self._headers(), json={"isRead": True}, timeout=15
            )
            resp.raise_for_status()
            return {"success": True, "message_id": message_id}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def delete_email(self, message_id: str) -> Dict:
        try:
            resp = requests.delete(f"{GRAPH_URL}/me/messages/{message_id}", headers=self._headers(), timeout=15)
            resp.raise_for_status()
            return {"success": True, "message_id": message_id}
        except Exception as e:
            return {"success": False, "error": str(e)}
