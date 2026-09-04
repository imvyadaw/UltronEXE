"""Short-term memory package with backward-compatible public exports."""

from collections import deque


# ULTRON legacy/simple API retained for existing callers such as MemoryManager.
class ShortTermMemory:
    def __init__(self, capacity=50):
        self.items = deque(maxlen=capacity)

    def add(self, item):
        self.items.append(item)

    def recent(self, n=10):
        return list(self.items)[-n:]


from memory.short_term.buffer import (
    ConversationBuffer,
    get_conversation_buffer,
    get_short_term_memory,
)
from memory.short_term.slots import (
    ReferenceMemory,
    get_reference_memory,
)

__all__ = [
    "ShortTermMemory",
    "ConversationBuffer",
    "get_conversation_buffer",
    "get_short_term_memory",
    "ReferenceMemory",
    "get_reference_memory",
]
