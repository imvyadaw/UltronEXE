"""
Email (CONNECT)
================
Sends and reads mail directly over SMTP/IMAP - stdlib `smtplib` and
`imaplib`, no desktop mail client involved. This project doesn't have
a Phase 6 apps/*.py email automation class to contrast against the
way whatsapp.py and spotify.py in this same folder do; this is simply
the project's first email capability.

Credentials come from EMAIL_ADDRESS and EMAIL_PASSWORD (an app
password for providers like Gmail that require one, not the account's
main password) as environment variables - never hardcoded. Host/port
default to Gmail's but are overridable via EMAIL_SMTP_HOST/
EMAIL_SMTP_PORT/EMAIL_IMAP_HOST for other providers. Same
empty/failure-safe contract as the rest of this project: missing
credentials or any send/connect failure collapse to
{"success": False, ...} rather than an exception - stdlib modules
don't need an availability check the way `requests` does, so
is_available() here only checks credentials.

send()'s body can be drafted by PHASE_18_6_AI_AGENTS/AGENTS/writer.py
and reviewed by that phase's guard.py before it reaches this module,
same division of labor as CONNECT/whatsapp.py.
"""

import imaplib
import os
import smtplib
from email.header import decode_header
from email.mime.text import MIMEText
from email.utils import parseaddr
from typing import Dict, List, Optional

ADDRESS_ENV = "EMAIL_ADDRESS"
PASSWORD_ENV = "EMAIL_PASSWORD"
SMTP_HOST_ENV = "EMAIL_SMTP_HOST"
SMTP_PORT_ENV = "EMAIL_SMTP_PORT"
IMAP_HOST_ENV = "EMAIL_IMAP_HOST"

DEFAULT_SMTP_HOST = "smtp.gmail.com"
DEFAULT_SMTP_PORT = 587
DEFAULT_IMAP_HOST = "imap.gmail.com"
DEFAULT_TIMEOUT_SECONDS = 10


class EmailConnect:
    """Headless SMTP send / IMAP read. Use get_email()."""

    def is_available(self) -> bool:
        return bool(os.environ.get(ADDRESS_ENV)) and bool(os.environ.get(PASSWORD_ENV))

    def send(self, to: str, subject: str, body: str) -> Dict:
        """Sends a plain-text email. Returns
        {"success": bool, "error": Optional[str]}."""
        if not self.is_available():
            return {"success": False, "error": "credentials not configured"}
        if not to or not subject:
            return {"success": False, "error": "to and subject both required"}
        address = os.environ[ADDRESS_ENV]
        message = MIMEText(body or "")
        message["Subject"] = subject
        message["From"] = address
        message["To"] = to
        host = os.environ.get(SMTP_HOST_ENV, DEFAULT_SMTP_HOST)
        port = int(os.environ.get(SMTP_PORT_ENV, DEFAULT_SMTP_PORT))
        try:
            with smtplib.SMTP(host, port, timeout=DEFAULT_TIMEOUT_SECONDS) as server:
                server.starttls()
                server.login(address, os.environ[PASSWORD_ENV])
                server.sendmail(address, [to], message.as_string())
            return {"success": True, "error": None}
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    def read_unread(self, num: int = 5) -> List[Dict]:
        """Returns up to `num` unread messages from the inbox, most
        recent first, as {"from": str, "subject": str}. Empty list on
        missing credentials or any connection failure - same
        empty-on-failure contract as PHASE_18_5_SEARCH_ENGINE, not a
        promise that the inbox is actually empty."""
        if not self.is_available():
            return []
        address = os.environ[ADDRESS_ENV]
        host = os.environ.get(IMAP_HOST_ENV, DEFAULT_IMAP_HOST)
        try:
            with imaplib.IMAP4_SSL(host) as server:
                server.login(address, os.environ[PASSWORD_ENV])
                server.select("INBOX")
                status, data = server.search(None, "UNSEEN")
                if status != "OK":
                    return []
                ids = data[0].split()[-max(1, num) :]
                results: List[Dict] = []
                for msg_id in reversed(ids):
                    status, msg_data = server.fetch(msg_id, "(BODY.PEEK[HEADER.FIELDS (FROM SUBJECT)])")
                    if status != "OK" or not msg_data or not msg_data[0]:
                        continue
                    raw = msg_data[0][1].decode("utf-8", errors="replace")
                    results.append(self._parse_headers(raw))
                return results
        except Exception:
            return []

    @staticmethod
    def _parse_headers(raw: str) -> Dict:
        from_line, subject_line = "", ""
        for line in raw.splitlines():
            if line.lower().startswith("from:"):
                from_line = line[5:].strip()
            elif line.lower().startswith("subject:"):
                subject_line = line[8:].strip()
        try:
            decoded_subject = decode_header(subject_line)[0]
            subject = decoded_subject[0]
            if isinstance(subject, bytes):
                subject = subject.decode(decoded_subject[1] or "utf-8", errors="replace")
        except Exception:
            subject = subject_line
        return {"from": parseaddr(from_line)[1] or from_line, "subject": subject}


_email: Optional[EmailConnect] = None


def get_email() -> EmailConnect:
    global _email
    if _email is None:
        _email = EmailConnect()
    return _email
