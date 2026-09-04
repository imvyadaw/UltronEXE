"""
Email agent
===========
Send, read and search email over plain SMTP/IMAP (stdlib only - no
Google/Microsoft OAuth app registration required). Works with any
provider that allows SMTP/IMAP app-passwords (Gmail, Outlook, Yahoo,
custom IMAP hosts).

Configured entirely via .env, following config.py's existing pattern:
    EMAIL_ADDRESS=you@gmail.com
    EMAIL_PASSWORD=your_app_password
    IMAP_HOST=imap.gmail.com
    IMAP_PORT=993
    SMTP_HOST=smtp.gmail.com
    SMTP_PORT=587

Every method returns a JSON-serializable dict with either the requested
data or an {"error": ...} key, matching the rest of Ultron's tool style.
"""

import email
import imaplib
import os
import smtplib
from email.header import decode_header
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Dict, List

from agents.base_agent import BaseAgent


class EmailAgent(BaseAgent):
    """Send/read/search email via SMTP + IMAP."""

    capabilities = ["email", "gmail", "outlook", "smtp", "imap"]

    def __init__(self):
        super().__init__("email", "Send/read/search email over plain SMTP/IMAP")
        self.address = os.getenv("EMAIL_ADDRESS")
        self.password = os.getenv("EMAIL_PASSWORD")
        self.imap_host = os.getenv("IMAP_HOST", "imap.gmail.com")
        self.imap_port = int(os.getenv("IMAP_PORT", "993"))
        self.smtp_host = os.getenv("SMTP_HOST", "smtp.gmail.com")
        self.smtp_port = int(os.getenv("SMTP_PORT", "587"))

    def _require_config(self) -> Dict:
        if not self.address or not self.password:
            return {"error": "EMAIL_ADDRESS / EMAIL_PASSWORD not set in .env"}
        return {}

    def send_email(self, to: str, subject: str, body: str, cc: str = None) -> Dict:
        """Send a plain-text email."""
        cfg_error = self._require_config()
        if cfg_error:
            return cfg_error
        try:
            msg = MIMEMultipart()
            msg["From"] = self.address
            msg["To"] = to
            msg["Subject"] = subject
            if cc:
                msg["Cc"] = cc
            msg.attach(MIMEText(body, "plain"))

            recipients = [to] + ([cc] if cc else [])
            with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
                server.starttls()
                server.login(self.address, self.password)
                server.sendmail(self.address, recipients, msg.as_string())
            return {"success": True, "to": to, "subject": subject}
        except Exception as e:
            return {"error": str(e)}

    def _connect_imap(self):
        conn = imaplib.IMAP4_SSL(self.imap_host, self.imap_port)
        conn.login(self.address, self.password)
        return conn

    def _decode(self, raw) -> str:
        if raw is None:
            return ""
        parts = decode_header(raw)
        out = ""
        for text, enc in parts:
            if isinstance(text, bytes):
                out += text.decode(enc or "utf-8", errors="ignore")
            else:
                out += text
        return out

    def read_inbox(self, limit: int = 10, unread_only: bool = False) -> Dict:
        """List the most recent emails in the inbox."""
        cfg_error = self._require_config()
        if cfg_error:
            return cfg_error
        try:
            conn = self._connect_imap()
            conn.select("INBOX")
            criterion = "UNSEEN" if unread_only else "ALL"
            status, data = conn.search(None, criterion)
            if status != "OK":
                return {"error": "IMAP search failed"}

            ids = data[0].split()
            ids = ids[-limit:][::-1]

            messages: List[Dict] = []
            for msg_id in ids:
                status, msg_data = conn.fetch(msg_id, "(RFC822)")
                if status != "OK":
                    continue
                msg = email.message_from_bytes(msg_data[0][1])
                messages.append(
                    {
                        "id": msg_id.decode(),
                        "from": self._decode(msg.get("From")),
                        "subject": self._decode(msg.get("Subject")),
                        "date": msg.get("Date"),
                    }
                )
            conn.logout()
            return {"count": len(messages), "messages": messages}
        except Exception as e:
            return {"error": str(e)}

    def search_emails(self, query: str, limit: int = 10) -> Dict:
        """Search inbox subjects/senders for `query`."""
        cfg_error = self._require_config()
        if cfg_error:
            return cfg_error
        try:
            conn = self._connect_imap()
            conn.select("INBOX")
            status, data = conn.search(None, f'(OR SUBJECT "{query}" FROM "{query}")')
            if status != "OK":
                return {"error": "IMAP search failed"}

            ids = data[0].split()[-limit:][::-1]
            results: List[Dict] = []
            for msg_id in ids:
                status, msg_data = conn.fetch(msg_id, "(RFC822)")
                if status != "OK":
                    continue
                msg = email.message_from_bytes(msg_data[0][1])
                results.append(
                    {
                        "id": msg_id.decode(),
                        "from": self._decode(msg.get("From")),
                        "subject": self._decode(msg.get("Subject")),
                        "date": msg.get("Date"),
                    }
                )
            conn.logout()
            return {"query": query, "count": len(results), "results": results}
        except Exception as e:
            return {"error": str(e)}

    def get_email_body(self, msg_id: str) -> Dict:
        """Fetch the plain-text body of a single email by IMAP id."""
        cfg_error = self._require_config()
        if cfg_error:
            return cfg_error
        try:
            conn = self._connect_imap()
            conn.select("INBOX")
            status, msg_data = conn.fetch(msg_id.encode(), "(RFC822)")
            if status != "OK":
                return {"error": f"Could not fetch message {msg_id}"}
            msg = email.message_from_bytes(msg_data[0][1])

            body = ""
            if msg.is_multipart():
                for part in msg.walk():
                    if part.get_content_type() == "text/plain":
                        body = part.get_payload(decode=True).decode(errors="ignore")
                        break
            else:
                body = msg.get_payload(decode=True).decode(errors="ignore")

            conn.logout()
            return {"id": msg_id, "subject": self._decode(msg.get("Subject")), "body": body}
        except Exception as e:
            return {"error": str(e)}
