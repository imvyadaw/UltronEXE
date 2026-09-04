"""
Slack automation
===================
Uses Slack's slack:// deep-link scheme to jump directly to a
workspace/channel, falling back to typed messaging in the focused
channel when only a channel *name* (not IDs) is known.
"""

import time
import webbrowser
from typing import Dict

from apps.base_app import BaseApp


class SlackApp(BaseApp):
    """Open channels and send messages via Slack Desktop."""

    APP_NAME = "slack"
    PROCESS_NAMES = ["slack.exe", "slack"]
    EXE_HINTS = ["slack", "slack.exe"]

    def open_channel(self, team_id: str, channel_id: str) -> Dict:
        try:
            webbrowser.open(f"slack://channel?team={team_id}&id={channel_id}")
            return {"success": True, "team_id": team_id, "channel_id": channel_id}
        except Exception as e:
            return {"error": str(e)}

    def send_message_to_open_channel(self, message: str) -> Dict:
        """Sends into whichever channel is currently focused in Slack -
        use open_channel() first if you have team/channel IDs."""
        return self.type_and_send(message)

    def jump_to(self, query: str) -> Dict:
        """Ctrl+K quick-switcher, typed query, Enter to jump to a channel/DM by name."""
        opened = self.focus()
        if opened.get("error"):
            opened = self.open()
            if opened.get("error"):
                return opened
            time.sleep(1.5)
        self.press_key("ctrl+k")
        time.sleep(0.4)
        self.type_text(query)
        time.sleep(0.3)
        return self.press_key("enter")
