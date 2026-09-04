"""
Gmail integration
==================
integration/ client for Gmail, so it sits alongside the other Phase 11
integrations with the same {"success": bool, ...} convention. Rather
than re-implementing Gmail's OAuth2 flow a second time, this subclasses
skills/email/gmail.py's GmailClient - which already does exactly that
(official Gmail API, same GMAIL_CREDENTIALS_PATH / GMAIL_TOKEN_PATH env
vars, same cached-token flow) - and adds a couple of mailbox-flavored
convenience methods on top.

Setup: see skills/email/gmail.py's docstring (Google Cloud project,
OAuth Client ID, GMAIL_CREDENTIALS_PATH/.env). This module doesn't need
separate credentials from the gmail_* skill tools - it's the same inbox.
"""

from typing import Dict

from skills.email.gmail import GmailClient


class Mailbox(GmailClient):
    """Gmail inbox access for the integration/ layer - send/read/search/
    manage are all inherited from GmailClient; the methods below are
    small mailbox-shaped conveniences on top."""

    def unread_count(self) -> Dict:
        result = self.read_emails(max_results=100, unread_only=True)
        if not result.get("success"):
            return result
        return {"success": True, "unread_count": result["count"]}

    def latest(self, max_results: int = 5) -> Dict:
        """Most recent emails regardless of read state - a quick
        "what's new" glance, as opposed to read_emails()'s fuller options."""
        return self.read_emails(max_results=max_results, unread_only=False)
