"""
Gmail skill
===========
Send, read, search and manage Gmail messages via the official Gmail API
(OAuth2 - no password/IMAP hacks). Mirrors the dict-return convention used
across skills/ (`{"success": True, ...}` / `{"success": False, "error": ...}`).

Setup (one-time):
    1. Create a Google Cloud project, enable the "Gmail API".
    2. Create an OAuth Client ID (Desktop app) and download the JSON as
       storage/cache/gmail_credentials.json (path overridable via
       GMAIL_CREDENTIALS_PATH in .env).
    3. First call opens a browser for consent; the resulting token is
       cached at storage/cache/gmail_token.json (GMAIL_TOKEN_PATH) so
       future calls don't re-prompt.
"""

import base64
import os
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from pathlib import Path
from typing import Dict, Optional

try:
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build

    HAS_GOOGLE = True
except ImportError:
    HAS_GOOGLE = False

BASE_DIR = Path(__file__).resolve().parent.parent.parent
SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]


class GmailClient:
    """Thin wrapper around the Gmail API for send/read/search/manage."""

    def __init__(self, credentials_path: Optional[str] = None, token_path: Optional[str] = None):
        self.credentials_path = Path(
            credentials_path
            or os.getenv("GMAIL_CREDENTIALS_PATH", BASE_DIR / "storage" / "cache" / "gmail_credentials.json")
        )
        self.token_path = Path(
            token_path or os.getenv("GMAIL_TOKEN_PATH", BASE_DIR / "storage" / "cache" / "gmail_token.json")
        )
        self._service = None

    # -- auth -----------------------------------------------------------
    def _get_service(self):
        if not HAS_GOOGLE:
            raise RuntimeError(
                "Gmail support needs: pip install google-api-python-client google-auth-httplib2 google-auth-oauthlib"
            )
        if self._service is not None:
            return self._service

        creds = None
        if self.token_path.exists():
            creds = Credentials.from_authorized_user_file(str(self.token_path), SCOPES)

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                if not self.credentials_path.exists():
                    raise FileNotFoundError(
                        f"Gmail OAuth client not found at {self.credentials_path}. "
                        "Download it from Google Cloud Console (OAuth Client ID -> Desktop app)."
                    )
                flow = InstalledAppFlow.from_client_secrets_file(str(self.credentials_path), SCOPES)
                creds = flow.run_local_server(port=0)
            self.token_path.parent.mkdir(parents=True, exist_ok=True)
            self.token_path.write_text(creds.to_json())

        self._service = build("gmail", "v1", credentials=creds)
        return self._service

    def is_configured(self) -> bool:
        return HAS_GOOGLE and self.credentials_path.exists()

    # -- send -------------------------------------------------------------
    def send_email(
        self, to: str, subject: str, body: str, cc: Optional[str] = None, bcc: Optional[str] = None, html: bool = False
    ) -> Dict:
        """Send an email. `body` is treated as HTML if html=True, else plain text."""
        try:
            service = self._get_service()
            message = MIMEMultipart()
            message["to"] = to
            message["subject"] = subject
            if cc:
                message["cc"] = cc
            if bcc:
                message["bcc"] = bcc
            message.attach(MIMEText(body, "html" if html else "plain"))

            raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
            sent = service.users().messages().send(userId="me", body={"raw": raw}).execute()
            return {"success": True, "message_id": sent.get("id"), "to": to, "subject": subject}
        except Exception as e:
            return {"success": False, "error": str(e)}

    # -- read / search ------------------------------------------------------
    def read_emails(self, max_results: int = 10, label: str = "INBOX", unread_only: bool = False) -> Dict:
        """List recent emails with sender/subject/snippet."""
        try:
            service = self._get_service()
            query = "is:unread" if unread_only else None
            resp = (
                service.users()
                .messages()
                .list(userId="me", labelIds=[label], maxResults=max_results, q=query)
                .execute()
            )
            messages = resp.get("messages", [])
            results = [self._get_message_summary(service, m["id"]) for m in messages]
            return {"success": True, "count": len(results), "emails": results}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def search_emails(self, query: str, max_results: int = 10) -> Dict:
        """Search using Gmail's native search syntax, e.g. 'from:boss@x.com is:unread'."""
        try:
            service = self._get_service()
            resp = service.users().messages().list(userId="me", q=query, maxResults=max_results).execute()
            messages = resp.get("messages", [])
            results = [self._get_message_summary(service, m["id"]) for m in messages]
            return {"success": True, "count": len(results), "emails": results}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _get_message_summary(self, service, msg_id: str) -> Dict:
        msg = (
            service.users()
            .messages()
            .get(userId="me", id=msg_id, format="metadata", metadataHeaders=["From", "Subject", "Date"])
            .execute()
        )
        headers = {h["name"]: h["value"] for h in msg.get("payload", {}).get("headers", [])}
        return {
            "id": msg_id,
            "from": headers.get("From", ""),
            "subject": headers.get("Subject", ""),
            "date": headers.get("Date", ""),
            "snippet": msg.get("snippet", ""),
        }

    # -- manage -------------------------------------------------------------
    def mark_as_read(self, message_id: str) -> Dict:
        try:
            service = self._get_service()
            service.users().messages().modify(userId="me", id=message_id, body={"removeLabelIds": ["UNREAD"]}).execute()
            return {"success": True, "message_id": message_id}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def delete_email(self, message_id: str) -> Dict:
        try:
            service = self._get_service()
            service.users().messages().trash(userId="me", id=message_id).execute()
            return {"success": True, "message_id": message_id, "action": "moved to trash"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_email_body(self, message_id: str) -> Dict:
        """Fetch the full plain-text body of one message."""
        try:
            service = self._get_service()
            msg = service.users().messages().get(userId="me", id=message_id, format="full").execute()
            body = self._extract_body(msg.get("payload", {}))
            return {"success": True, "message_id": message_id, "body": body}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _extract_body(self, payload: Dict) -> str:
        if payload.get("mimeType") == "text/plain" and "data" in payload.get("body", {}):
            return base64.urlsafe_b64decode(payload["body"]["data"]).decode(errors="ignore")
        for part in payload.get("parts", []) or []:
            text = self._extract_body(part)
            if text:
                return text
        return ""
