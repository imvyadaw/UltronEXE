"""
Microsoft Outlook automation
==============================
GUI app control plus mailto:-based compose (works even without the
desktop app configured, via the OS default mail handler). For actually
sending mail headlessly via SMTP/Graph, see agents/email_agent.py or
skills/email/outlook.py instead - this module drives the desktop app.
"""

import time
import webbrowser
from typing import Dict, List, Optional
from urllib.parse import quote

from apps.base_app import BaseApp


class OutlookApp(BaseApp):
    """Open Outlook, compose mail, and jump to the calendar/inbox."""

    APP_NAME = "outlook"
    PROCESS_NAMES = ["outlook.exe", "outlook"]
    EXE_HINTS = ["outlook", "outlook.exe"]

    def compose_email(self, to: str, subject: str = "", body: str = "", cc: Optional[List[str]] = None) -> Dict:
        try:
            params = [f"subject={quote(subject)}", f"body={quote(body)}"]
            if cc:
                params.append(f"cc={quote(','.join(cc))}")
            mailto = f"mailto:{quote(to)}?{'&'.join(params)}"
            webbrowser.open(mailto)
            return {"success": True, "to": to, "subject": subject}
        except Exception as e:
            return {"error": str(e)}

    def open_inbox(self) -> Dict:
        return self.open()

    def open_calendar(self) -> Dict:
        opened = self.open()
        if opened.get("error"):
            return opened
        time.sleep(1.5)
        return self.press_key("ctrl+2")

    def new_meeting(self) -> Dict:
        opened = self.open()
        if opened.get("error"):
            return opened
        time.sleep(1.5)
        return self.press_key("ctrl+shift+q")
