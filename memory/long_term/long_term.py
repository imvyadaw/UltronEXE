"""Long-term memory
================
Durable, structured facts Ultron learns about the user over time
(distinct from the flat quick-notes list in memory/short_term/notes.py).
Backed by SQLite so it survives restarts. Each fact has a category
(e.g. "preference", "person", "reminder") and a key, so the same fact
can be looked up or overwritten later.

Storage mechanics (schema, connection, raw SQL) now live in
memory/long_term/storage.SQLiteStorage - this class keeps the
store()/get()/search()/list_all()/forget() vocabulary every existing
caller (ai/rag_engine.py, agents/memory_agent.py, ...) already uses, just
implemented on top of that shared, reusable storage engine instead of
duplicating the sqlite3 wiring here.
"""

from typing import Dict, List, Optional

from memory.long_term.storage import SQLiteStorage


class LongTermMemory:
    """Store/retrieve durable structured facts about the user."""

    def __init__(self):
        self._storage = SQLiteStorage(table="facts")

    def store(self, key: str, value: str, category: str = "general") -> Dict:
        """Store or overwrite a fact under (category, key)."""
        result = self._storage.set(key, value, category)
        if "error" in result:
            return result
        return {"success": True, "category": category, "key": key, "value": value}

    def get(self, key: str, category: str = "general") -> Dict:
        """Retrieve a single fact by (category, key)."""
        try:
            value = self._storage.get(key, category)
            if value is None:
                return {"error": f"No fact found for {category}/{key}"}
            # storage.get() doesn't return updated_at - fetch it via list_category
            # rather than adding a second SQL round trip type to SQLiteStorage.
            for row in self._storage.list_category(category):
                if row["key"] == key:
                    return {"category": category, "key": key, "value": row["value"], "updated_at": row["updated_at"]}
            return {"category": category, "key": key, "value": value, "updated_at": None}
        except Exception as e:
            return {"error": str(e)}

    def search(self, query: str, category: Optional[str] = None) -> Dict:
        """Search facts whose key or value contains `query`."""
        try:
            results = self._storage.search(query)
            if category:
                results = [r for r in results if r["category"] == category]
            return {"query": query, "count": len(results), "results": results}
        except Exception as e:
            return {"error": str(e)}

    def list_all(self, category: Optional[str] = None) -> Dict:
        """List all stored facts, optionally filtered by category."""
        try:
            if category:
                facts = self._storage.list_category(category)
                facts = [{"category": category, **f} for f in facts]
            else:
                facts = []
                for cat in self._storage.all_categories():
                    facts.extend({"category": cat, **f} for f in self._storage.list_category(cat))
            return {"count": len(facts), "facts": facts}
        except Exception as e:
            return {"error": str(e)}

    def forget(self, key: str, category: str = "general") -> Dict:
        """Delete a stored fact."""
        return self._storage.delete(key, category)

    def all_facts(self) -> List[Dict]:
        """List every stored fact as {subject, predicate, value, updated_at} -
        "subject" is the fact's key and "predicate" is its category, matching
        the subject/predicate terminology memory/forget.py's cascade logic
        uses across all of memory/."""
        facts = self.list_all().get("facts", [])
        return [
            {
                "subject": f["key"],
                "predicate": f["category"],
                "value": f.get("value"),
                "updated_at": f.get("updated_at"),
            }
            for f in facts
        ]

    def _delete_fact(self, subject: str, predicate: Optional[str] = None) -> int:
        """Delete every stored fact whose key matches `subject`, optionally
        narrowed to one category via `predicate`. Returns the number of
        facts removed. Private primitive - only memory/forget.py should call
        this; everything else uses the public forget(key, category) above."""
        removed = 0
        for fact in self.all_facts():
            if fact["subject"] != subject:
                continue
            if predicate is not None and fact["predicate"] != predicate:
                continue
            result = self._storage.delete(fact["subject"], fact["predicate"])
            if "error" not in result:
                removed += 1
        return removed


_long_term_memory: Optional["LongTermMemory"] = None


def get_long_term_memory() -> "LongTermMemory":
    global _long_term_memory
    if _long_term_memory is None:
        _long_term_memory = LongTermMemory()
    return _long_term_memory
