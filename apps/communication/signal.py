"""
Signal automation
====================
Signal Desktop has no public deep-link scheme for jumping to a specific
chat, so this module is limited to open/focus + generic
type-into-whatever's-focused messaging (caller is responsible for having
the right conversation already open).
"""

from typing import Dict

from apps.base_app import BaseApp


class SignalApp(BaseApp):
    """Open Signal Desktop and send a message into the focused chat."""

    APP_NAME = "signal"
    PROCESS_NAMES = ["signal.exe", "signal"]
    EXE_HINTS = ["signal", "signal.exe"]

    def send_message_to_open_chat(self, message: str) -> Dict:
        """Sends into whichever chat is currently open/focused in Signal -
        there's no deep link to select a contact, so open the right
        conversation first."""
        return self.type_and_send(message)
