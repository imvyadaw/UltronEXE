"""
History
=======
Every module upstream already keeps its own log for its own reason -
consciousness.py's introspection log (why attention moved),
habit_memory.py's action log (pattern mining), forget.py's audit log
(accountability). history.py doesn't add a fourth log; it merges the
existing ones (plus long_term.py's fact timestamps) into one
chronological view, because "what has Ultron been doing" is a question
about all of them together, not any one in isolation, and nobody
should have to check four modules to answer it.

Read-only, same as dashboard.py - this module writes nothing to any
of the sources it reads from. One honesty note: habit entries don't
carry a real occurrence timestamp (detected_habits() reports a mined
pattern, not a single event), so they're stamped with "now" at query
time and will always sort as most-recent - callers that need true
event ordering should filter kinds to exclude "habit".
"""

import time
from typing import Dict, List, Optional


class History:
    """Merged, chronological activity timeline. Use get_history()."""

    def timeline(self, limit: int = 50, kinds: Optional[List[str]] = None) -> List[Dict]:
        """kinds filters to any subset of {"focus", "habit", "forget",
        "fact"}; None (default) includes all four. Entries are sorted
        newest-first."""
        kinds = kinds or ["focus", "habit", "forget", "fact"]
        events: List[Dict] = []

        if "focus" in kinds:
            events.extend(self._focus_events())
        if "habit" in kinds:
            events.extend(self._habit_events())
        if "forget" in kinds:
            events.extend(self._forget_events())
        if "fact" in kinds:
            events.extend(self._fact_events())

        events.sort(key=lambda e: e["timestamp"], reverse=True)
        return events[:limit]

    @staticmethod
    def _focus_events() -> List[Dict]:
        try:
            from core.consciousness_p18 import get_consciousness

            notes = get_consciousness().recent_notes(limit=50)
            return [
                {"kind": "focus", "summary": n["event"], "timestamp": n["timestamp"], "meta": n["meta"]} for n in notes
            ]
        except Exception:
            return []

    @staticmethod
    def _habit_events() -> List[Dict]:
        try:
            from memory.habit_memory import get_habit_memory

            habits = get_habit_memory().detected_habits()
            now = time.time()
            return [
                {
                    "kind": "habit",
                    "summary": f"pattern: {h['action']} ({h['occurrences']}x)",
                    "timestamp": now,
                    "meta": h,
                }
                for h in habits
            ]
        except Exception:
            return []

    @staticmethod
    def _forget_events() -> List[Dict]:
        try:
            from memory.forget import get_forgetter

            entries = get_forgetter().audit_log(limit=50)
            return [
                {
                    "kind": "forget",
                    "summary": f"{e['operation']}: {e['target']}",
                    "timestamp": e["logged_at"],
                    "meta": e,
                }
                for e in entries
            ]
        except Exception:
            return []

    @staticmethod
    def _fact_events() -> List[Dict]:
        try:
            from memory.long_term import get_long_term_memory

            facts = get_long_term_memory().all_facts()
            return [
                {
                    "kind": "fact",
                    "summary": f"{f['subject']} {f['predicate']} {f['value']}",
                    "timestamp": f["last_seen"],
                    "meta": f,
                }
                for f in facts
            ]
        except Exception:
            return []


_history: Optional[History] = None


def get_history() -> History:
    global _history
    if _history is None:
        _history = History()
    return _history
