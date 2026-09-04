"""
Memory
======
Unified memory API spanning short_term/, long_term/, and vector_db/ -
one place to remember/recall from, instead of the caller needing to
know which of the three backends holds what. Thin - the real logic
lives in each backend module; this just picks the right one per call.
"""

from typing import Dict

from memory.short_term.notes import NotesStore
from memory.long_term.long_term import LongTermMemory
from memory.vector_db.vector_store import VectorStore


class MemoryStore:
    """One `remember`/`recall` surface over all three memory backends."""

    def __init__(self):
        self._notes = NotesStore()
        self._long_term = LongTermMemory()
        self._vectors = VectorStore()

    def remember(self, key: str, value: str, category: str = "general", searchable: bool = True) -> Dict:
        """Store a durable fact under `key` (long-term), and optionally also
        index it for similarity search (vector memory) so it can be found
        later without knowing the exact key."""
        result = self._long_term.store(key, value, category)
        if searchable and "error" not in result:
            self._vectors.add(f"{key}: {value}", category)
        return result

    def recall(self, key: str, category: str = "general") -> Dict:
        """Look up a fact by its exact key (long-term memory)."""
        return self._long_term.get(key, category)

    def recall_similar(self, query: str, top_k: int = 5) -> Dict:
        """Find previously remembered things similar in meaning to `query`,
        without needing to know the exact key (vector memory)."""
        return self._vectors.similarity_search(query, top_k)

    def quick_note(self, text: str) -> Dict:
        """Flat timestamped note - for a quick jotting, not a structured fact."""
        return self._notes.save_note(text)

    def all_notes(self) -> Dict:
        return self._notes.read_notes()

    def forget(self, key: str, category: str = "general") -> Dict:
        """Delete a remembered fact."""
        return self._long_term.forget(key, category)
