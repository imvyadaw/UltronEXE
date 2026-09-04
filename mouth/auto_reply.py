"""
Auto Reply
==========
A small fixed-vocabulary quick-reply table for latency-sensitive
one-liners, same "cheap heuristic over an extra round-trip for
something this bounded" call COMMAND/control_panel.py's execute()
already makes for admin commands - this is that same idea for spoken
small talk instead of admin phrases. try_reply() either returns an
immediate answer or None; None means "not in the fixed vocabulary,
fall through to the real reasoning pipeline" - this module never
guesses at an answer it doesn't have a fixed entry for.

Time/date entries are computed live (there's no sense caching those);
greeting/small-talk entries are static strings. Matching is
case-insensitive substring, same normalization style
control_panel.execute() uses.
"""

from datetime import datetime
from typing import List, Optional

STATIC_REPLIES = {
    "hello": "Hey - what can I do for you?",
    "hi": "Hey - what can I do for you?",
    "how are you": "Running well, thanks for asking.",
    "thank you": "Anytime.",
    "thanks": "Anytime.",
    "good morning": "Good morning.",
    "good night": "Good night.",
}


class AutoReply:
    """Fixed-vocabulary quick replies. Use get_auto_reply()."""

    def __init__(self):
        self._dynamic: List[tuple] = [
            (lambda t: "time" in t, self._say_time),
            (lambda t: "date" in t or "day is it" in t, self._say_date),
        ]

    def try_reply(self, text: str) -> Optional[str]:
        """Returns an immediate reply, or None if `text` doesn't match
        anything in the fixed vocabulary."""
        if not text:
            return None
        normalized = text.strip().lower()

        for phrase, reply in STATIC_REPLIES.items():
            if phrase in normalized:
                return reply

        for matcher, handler in self._dynamic:
            if matcher(normalized):
                return handler()

        return None

    @staticmethod
    def _say_time() -> str:
        return f"It's {datetime.now().strftime('%I:%M %p').lstrip('0')}."

    @staticmethod
    def _say_date() -> str:
        return f"It's {datetime.now().strftime('%A, %B %d')}."

    @staticmethod
    def known_phrases() -> List[str]:
        return list(STATIC_REPLIES.keys()) + ["<time query>", "<date query>"]


_auto_reply: Optional[AutoReply] = None


def get_auto_reply() -> AutoReply:
    global _auto_reply
    if _auto_reply is None:
        _auto_reply = AutoReply()
    return _auto_reply
