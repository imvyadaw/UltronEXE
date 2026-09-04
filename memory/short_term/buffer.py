"""Conversation buffer
===================
An in-memory, fixed-size ring buffer of the most recent conversation
turns - the "what did we just say" layer, distinct from:
    - memory/short_term/notes.py: user-saved quick notes (explicit "remember this").
    - memory/history/history.py: full past sessions persisted to SQLite.
    - memory/history/tracker.py: per-interaction command/tool audit log.
    - ai.ai_router.AIRouter.history: the actual live list the LLM client
      reads for context on its next turn (this buffer does NOT replace
      that - it's a read-only convenience view for other modules, e.g.
      ai/rag_engine.py or a dashboard, that want "the last N turns"
      without importing the router).

Deliberately not persisted - by definition this is *short*-term. Nothing
here is lost, though: every turn that lands in this buffer also already
went into ai.ai_router.AIRouter.history (source of truth for the live
session) and, once a session ends, memory/history/history.py.
"""

import time
from collections import deque
from typing import Dict, List, Optional

DEFAULT_MAX_TURNS = 20


class ConversationBuffer:
    """Fixed-size ring buffer of recent {"role", "content", "timestamp"} turns."""

    def __init__(self, max_turns: int = DEFAULT_MAX_TURNS):
        self.max_turns = max_turns
        self._buffer: deque = deque(maxlen=max_turns)

    def add(self, role: str, content: str) -> None:
        """Append one turn (role is "user" or "assistant")."""
        self._buffer.append({"role": role, "content": content, "timestamp": time.time()})

    def add_exchange(self, user_message: str, assistant_response: str) -> None:
        """Convenience for the common case of logging a full user+reply pair."""
        self.add("user", user_message)
        self.add("assistant", assistant_response)

    def recent(self, n: Optional[int] = None) -> List[Dict]:
        """The most recent `n` turns (default: everything currently buffered),
        oldest first - ready to hand straight to an LLM client as history."""
        items = list(self._buffer)
        if n is not None:
            items = items[-n:]
        return items

    def as_plain_messages(self, n: Optional[int] = None) -> List[Dict[str, str]]:
        """Same as recent(), but stripped of the timestamp - the exact
        {"role", "content"} shape ai/llm/ clients and ai.ai_router expect."""
        return [{"role": t["role"], "content": t["content"]} for t in self.recent(n)]

    def last_user_message(self) -> Optional[str]:
        for turn in reversed(self._buffer):
            if turn["role"] == "user":
                return turn["content"]
        return None

    def clear(self) -> None:
        self._buffer.clear()

    def snapshot(self) -> Dict:
        """Small dashboard-friendly summary - turn count plus the recent
        turns themselves, without exposing the deque or internal state."""
        return {
            "turn_count": len(self._buffer),
            "max_turns": self.max_turns,
            "recent": self.recent(),
        }

    def __len__(self) -> int:
        return len(self._buffer)


_buffer: Optional[ConversationBuffer] = None


def get_conversation_buffer() -> ConversationBuffer:
    """Process-wide singleton, mirroring ai.ai_router.get_router()."""
    global _buffer
    if _buffer is None:
        _buffer = ConversationBuffer()
    return _buffer


# Alias: memory/forget.py and command/dashboard.py both look up the
# short-term layer as `get_short_term_memory` (matching the naming
# pattern of get_long_term_memory/get_face_memory/get_place_memory/
# get_habit_memory in the rest of memory/) rather than
# `get_conversation_buffer`. Same singleton, just exported under the
# name those callers actually import.
get_short_term_memory = get_conversation_buffer
