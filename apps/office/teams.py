"""
Microsoft Teams automation
=============================
Uses Teams' msteams: deep-link scheme for chat/call/meeting where
possible (works even if the desktop client isn't already running - the
protocol handler launches it).
"""

import webbrowser
from typing import Dict

from apps.base_app import BaseApp


class TeamsApp(BaseApp):
    """Open Teams, jump to a chat, or start/join a meeting."""

    APP_NAME = "teams"
    PROCESS_NAMES = ["teams.exe", "ms-teams.exe", "teams"]
    EXE_HINTS = ["teams", "ms-teams.exe"]

    def open_chat(self, email: str) -> Dict:
        try:
            webbrowser.open(f"msteams:/l/chat/0/0?users={email}")
            return {"success": True, "email": email}
        except Exception as e:
            return {"error": str(e)}

    def join_meeting(self, meeting_url: str) -> Dict:
        try:
            webbrowser.open(meeting_url)
            return {"success": True, "meeting_url": meeting_url}
        except Exception as e:
            return {"error": str(e)}

    def start_call(self, email: str, video: bool = False) -> Dict:
        try:
            kind = "call" if not video else "call?withVideo=true"
            webbrowser.open(f"msteams:/l/call/0/0?users={email}&{('video=true' if video else '')}")
            return {"success": True, "email": email, "video": video}
        except Exception as e:
            return {"error": str(e)}
