"""
Memory agent
============
Thin wrapper over all three memory backends: short-term quick notes,
long-term structured facts, and vector-similarity search - so callers
that want direct memory access (without going through the LLM
tool-calling loop) have one place to reach for it.
"""

from memory.short_term.notes import NotesStore
from memory.long_term.long_term import LongTermMemory
from memory.vector_db.vector_store import VectorStore
from memory.history.history import ConversationHistoryStore
from agents.base_agent import BaseAgent


class MemoryAgent(BaseAgent):
    capabilities = ["memory", "notes", "recall", "facts"]

    def __init__(self):
        super().__init__("memory", "Short-term notes, long-term facts, and vector-similarity search")
        self.notes = NotesStore()
        self.long_term = LongTermMemory()
        self.vectors = VectorStore()
        self.history = ConversationHistoryStore()

    def remember(self, text: str):
        """Quick note (short-term, flat list)."""
        return self.notes.save_note(text)

    def recall_all(self):
        """All quick notes."""
        return self.notes.read_notes()

    def remember_fact(self, key: str, value: str, category: str = "general"):
        """Durable structured fact (long-term)."""
        return self.long_term.store(key, value, category)

    def recall_fact(self, key: str, category: str = "general"):
        """Look up a durable fact by key."""
        return self.long_term.get(key, category)

    def remember_for_search(self, text: str, category: str = "general"):
        """Store text for later similarity search (vector memory)."""
        return self.vectors.add(text, category)

    def search_memory(self, query: str, top_k: int = 5):
        """Find past notes/facts most similar to a query."""
        return self.vectors.similarity_search(query, top_k)

    def save_conversation(self, messages: list):
        """Persist a full conversation session."""
        return self.history.save_session(messages)
