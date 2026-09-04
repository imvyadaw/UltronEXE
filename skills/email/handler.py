"""
Email skill (Phase 4 facade)
=============================
One entry point over Gmail + Outlook + templates (skills/email/gmail.py,
outlook.py, templates.py), auto-picking whichever provider is configured
so the AI only needs one "send"/"read"/"search" action instead of two
provider-specific tool names. Pass provider="gmail"/"outlook" to force one.
"""

from typing import Dict, Optional

from skills.base_skill import BaseSkill
from skills.email.gmail import GmailClient
from skills.email.outlook import OutlookClient
from skills.email.templates import EmailTemplates


class EmailHandler(BaseSkill):
    """Provider-agnostic send/read/search/manage + template rendering for email."""

    name = "email"
    description = "Send, read, search, and manage email (Gmail/Outlook), plus reusable templates."
    category = "communication"

    def __init__(self, provider: str = "auto"):
        self.provider = provider
        self._gmail = GmailClient()
        self._outlook = OutlookClient()
        self._templates = EmailTemplates()
        super().__init__()

    # -- provider selection -------------------------------------------------
    def _client(self, provider: Optional[str] = None):
        provider = (provider or self.provider or "auto").lower()
        if provider == "gmail":
            return self._gmail
        if provider == "outlook":
            return self._outlook
        if self._gmail.is_configured():
            return self._gmail
        if self._outlook.is_configured():
            return self._outlook
        raise RuntimeError(
            "No email provider configured - set up Gmail OAuth credentials or "
            "OUTLOOK_CLIENT_ID (see skills/email/gmail.py / outlook.py docstrings)."
        )

    # -- send/read/search/manage ---------------------------------------------
    def send_email(
        self,
        to: str,
        subject: str,
        body: str,
        cc: Optional[str] = None,
        html: bool = False,
        provider: Optional[str] = None,
    ) -> Dict:
        return self._client(provider).send_email(to=to, subject=subject, body=body, cc=cc, html=html)

    def read_emails(self, max_results: int = 10, unread_only: bool = False, provider: Optional[str] = None) -> Dict:
        return self._client(provider).read_emails(max_results=max_results, unread_only=unread_only)

    def search_emails(self, query: str, max_results: int = 10, provider: Optional[str] = None) -> Dict:
        return self._client(provider).search_emails(query=query, max_results=max_results)

    def mark_as_read(self, message_id: str, provider: Optional[str] = None) -> Dict:
        return self._client(provider).mark_as_read(message_id)

    def delete_email(self, message_id: str, provider: Optional[str] = None) -> Dict:
        return self._client(provider).delete_email(message_id)

    def get_email_body(self, message_id: str, provider: Optional[str] = None) -> Dict:
        client = self._client(provider)
        if not hasattr(client, "get_email_body"):
            return {"success": False, "error": "Fetching the full body is currently only implemented for Gmail."}
        return client.get_email_body(message_id)

    # -- templates ------------------------------------------------------
    def send_from_template(self, to: str, template_name: str, provider: Optional[str] = None, **fields) -> Dict:
        rendered = self._templates.render(template_name, **fields)
        if not rendered.get("success"):
            return rendered
        return self.send_email(to=to, subject=rendered["subject"], body=rendered["body"], provider=provider)

    def register_actions(self) -> None:
        t = self._templates
        self._actions = {
            "send": self.send_email,
            "read": self.read_emails,
            "search": self.search_emails,
            "mark_read": self.mark_as_read,
            "delete": self.delete_email,
            "get_body": self.get_email_body,
            "send_from_template": self.send_from_template,
            "list_templates": t.list_templates,
            "get_template": t.get_template,
            "save_template": t.save_template,
            "delete_template": t.delete_template,
        }

    def health_check(self) -> Dict:
        return {
            "success": True,
            "skill": self.name,
            "gmail_configured": self._gmail.is_configured(),
            "outlook_configured": self._outlook.is_configured(),
        }
