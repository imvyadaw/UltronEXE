"""
Context engine
==============
Rolling memory of proactive turns: each time Ultron says something
unprompted (proactive/engine.py) or a scenario runs
(scenarios/morning_routine.py etc.), it's recorded here as a Turn. When
the user replies, intent_analyzer.py and response_builder.py look back
at the most recent turn to answer "what is this reply about" - e.g.
after a "battery_low" alert, a bare "later" means "remind me later
about the battery", not a new unrelated request.

Deliberately in-memory + bounded (MAX_TURNS), not persisted - this is
short-horizon conversational glue for the current session, not a
long-term memory store (that's core/memory.py, backed by
memory/long_term/ and memory/vector_db/, which this does NOT duplicate
or replace).
"""

import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional

MAX_TURNS = 30


@dataclass
class Turn:
    category: str  # e.g. "battery_low", "morning_briefing"
    text: str  # what Ultron said
    kwargs: Dict = field(default_factory=dict)  # the data behind the phrase (percent=18, etc.)
    timestamp: float = field(default_factory=time.time)
    user_reply: Optional[str] = None
    resolved: bool = False  # user acknowledged/dismissed/acted on it


class ConversationContextEngine:
    """Bounded rolling history of proactive turns for this session."""

    def __init__(self, max_turns: int = MAX_TURNS):
        self._turns: List[Turn] = []
        self._max_turns = max_turns

    def record_turn(self, category: str, text: str, kwargs: Optional[Dict] = None) -> Turn:
        turn = Turn(category=category, text=text, kwargs=kwargs or {})
        self._turns.append(turn)
        if len(self._turns) > self._max_turns:
            self._turns.pop(0)
        return turn

    def last_turn(self) -> Optional[Turn]:
        return self._turns[-1] if self._turns else None

    def last_unresolved_turn(self, within_seconds: float = 300) -> Optional[Turn]:
        """Most recent turn that hasn't been marked resolved and is still
        "fresh" (within `within_seconds`) - a reply five minutes after a
        battery warning is far more likely a new topic than a response to
        it, so intent_analyzer.py shouldn't force a link that's gone stale."""
        now = time.time()
        for turn in reversed(self._turns):
            if turn.resolved:
                continue
            if now - turn.timestamp > within_seconds:
                return None
            return turn
        return None

    def record_reply(self, reply: str, resolved: bool = True) -> Optional[Turn]:
        """Attach the user's reply to the most recent unresolved turn, if any."""
        turn = self.last_unresolved_turn()
        if turn:
            turn.user_reply = reply
            turn.resolved = resolved
        return turn

    def history(self, limit: int = 10) -> List[Turn]:
        return self._turns[-limit:]

    def clear(self) -> None:
        self._turns.clear()


_engine: Optional[ConversationContextEngine] = None


def get_context_engine() -> ConversationContextEngine:
    global _engine
    if _engine is None:
        _engine = ConversationContextEngine()
    return _engine
