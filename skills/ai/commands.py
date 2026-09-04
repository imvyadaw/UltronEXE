"""
Command Processor for Ultron
============================
Handles special slash-commands (/help, /clear, /reset, ...), as distinct
from the AI tool-calling handled by core/executor.py.
"""

import os
import sys
import webbrowser
from typing import Callable, Dict, Optional, Tuple
from datetime import datetime


class CommandProcessor:
    """Processes special commands for Ultron. Commands are prefixed with '/'."""

    def __init__(self):
        self.commands: Dict[str, Callable] = {
            "help": self.cmd_help,
            "clear": self.cmd_clear,
            "reset": self.cmd_reset,
            "time": self.cmd_time,
            "date": self.cmd_date,
            "open": self.cmd_open,
            "search": self.cmd_search,
            "exit": self.cmd_exit,
            "quit": self.cmd_exit,
            "intelligence": self.cmd_intelligence,
            "intel": self.cmd_intelligence,
        }

        self.reset_callback: Optional[Callable] = None

    def set_reset_callback(self, callback: Callable):
        self.reset_callback = callback

    def is_command(self, text: str) -> bool:
        return text.strip().startswith("/")

    def process(self, text: str) -> Tuple[bool, Optional[str]]:
        text = text.strip()

        if text.startswith("/"):
            text = text[1:]

        parts = text.split(maxsplit=1)
        if not parts:
            return False, None

        cmd = parts[0].lower()
        args = parts[1] if len(parts) > 1 else ""

        if cmd in self.commands:
            return True, self.commands[cmd](args)

        return False, None

    def cmd_help(self, args: str) -> str:
        help_text = """
+------------------------------------------------------------------+
|                    ULTRON COMMAND CENTER                         |
+------------------------------------------------------------------+
|  /help          - Display this help message                      |
|  /clear         - Clear the terminal screen                       |
|  /reset         - Reset conversation history                      |
|  /time          - Get current time                                |
|  /date          - Get current date                                |
|  /open [url]    - Open a URL in browser                           |
|  /search [query]- Search Google for a query                       |
|  /intelligence  - Show Phase 19-20 intelligence layer status       |
|  /exit or /quit - Exit Ultron                                     |
+------------------------------------------------------------------+
"""
        return help_text

    def cmd_clear(self, args: str) -> str:
        os.system("cls" if os.name == "nt" else "clear")
        return "Terminal cleared, Sir."

    def cmd_reset(self, args: str) -> str:
        if self.reset_callback:
            self.reset_callback()
        return "Conversation history has been reset, Sir. Starting fresh."

    def cmd_time(self, args: str) -> str:
        now = datetime.now()
        return f"The current time is {now.strftime('%I:%M %p')}, Sir."

    def cmd_date(self, args: str) -> str:
        now = datetime.now()
        return f"Today is {now.strftime('%A, %B %d, %Y')}, Sir."

    def cmd_open(self, args: str) -> str:
        if not args:
            return "Please specify a URL to open, Sir."

        url = args.strip()
        if not url.startswith(("http://", "https://")):
            url = "https://" + url

        try:
            webbrowser.open(url)
            return f"Opening {url} in your browser, Sir."
        except Exception as e:
            return f"I apologize, Sir. I couldn't open that URL: {e}"

    def cmd_search(self, args: str) -> str:
        if not args:
            return "Please provide a search query, Sir."

        query = args.strip().replace(" ", "+")
        url = f"https://www.google.com/search?q={query}"

        try:
            webbrowser.open(url)
            return f"Searching Google for '{args.strip()}', Sir."
        except Exception as e:
            return f"I apologize, Sir. Search failed: {e}"

    def cmd_intelligence(self, args: str) -> str:
        """Phase 19.1-20.6 intelligence layer status - which of the 13
        bridges (world state, intent, goals, verification, healing,
        skill learning, knowledge, confidence, answer reader,
        conversation, proactive, predictive, performance) are live,
        plus the Phase 20.6 database layer and, with '/intelligence
        events', the most recent logged turns."""
        try:
            from intelligence import get_intelligence_core
        except Exception as e:
            return f"Intelligence layer not importable, Sir: {e}"

        core = get_intelligence_core()

        if args.strip().lower() == "events":
            events = core.get_recent_events(limit=5)
            if not events:
                return "No intelligence events logged yet, Sir."
            lines = [
                f"  - {e['user_input']!r} -> intent={e['intent']}, "
                f"confidence={e['confidence']}, clarify={e['should_clarify']}"
                for e in events
            ]
            return "Last logged turns, Sir:\n" + "\n".join(lines)

        status = core.status()
        bridges = status.get("bridges", {})
        up = [name for name, info in bridges.items() if info.get("available")]
        down = [name for name, info in bridges.items() if not info.get("available")]
        dbs = status.get("databases", {})
        db_up = sum(1 for d in dbs.values() if d.get("available"))

        lines = [
            f"Intelligence core: {'online' if status.get('intelligence_core_available') else 'OFFLINE'}, Sir.",
            f"Bridges up ({len(up)}/{len(bridges)}): {', '.join(up) or 'none'}",
        ]
        if down:
            lines.append(f"Bridges down: {', '.join(down)}")
        lines.append(f"Databases: {db_up}/{len(dbs)} available")
        return "\n".join(lines)

    def cmd_exit(self, args: str) -> str:
        print("\nGoodbye, Sir. ULTRON signing off.\n")
        sys.exit(0)


_processor: Optional[CommandProcessor] = None


def get_command_processor() -> CommandProcessor:
    global _processor
    if _processor is None:
        _processor = CommandProcessor()
    return _processor
