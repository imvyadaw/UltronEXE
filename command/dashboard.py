"""
Dashboard
=========
COMMAND/'s read-only front door - one aggregated snapshot of
everything Phase 18 now tracks, the same "single gathering point"
relationship brain.py has to core.brain, applied to status instead of
a conversational turn. Nothing here computes anything new; every field
is a best-effort call into a module that already owns that data
(consciousness.reflect(), personality.current_style(), each MEMORY/
module's own summary methods). A missing or erroring piece just means
that key is omitted from the result, matching consciousness.reflect()'s
own active_tasks handling - a dashboard that can partially render is
far more useful than one that throws because one subsystem (e.g.
vision/, still a stub) isn't available yet.

Note: current_place omits its key both when place_memory can't be
reached at all *and* when it legitimately has no match for where the
user currently is - snapshot() can't tell those apart, and doesn't try
to; a caller that needs to distinguish "unknown" from "unavailable"
should call place_memory.current_place() directly instead.
"""

from typing import Dict, Optional


class Dashboard:
    """Aggregated read-only status snapshot. Use get_dashboard()."""

    def snapshot(self) -> Dict:
        fields = {
            "consciousness": self._consciousness,
            "personality": self._personality,
            "short_term": self._short_term,
            "long_term_fact_count": self._long_term_count,
            "known_people": self._known_people,
            "known_places": self._known_places,
            "current_place": self._current_place,
            "detected_habits": self._detected_habits,
            "mood_trend": self._mood_trend,
        }
        result = {}
        for key, getter in fields.items():
            value = getter()
            if value is not None:
                result[key] = value
        return result

    @staticmethod
    def _consciousness() -> Optional[Dict]:
        try:
            from core.consciousness_p18 import get_consciousness

            return get_consciousness().reflect()
        except Exception:
            return None

    @staticmethod
    def _personality() -> Optional[Dict]:
        try:
            from core.personality import get_personality

            return get_personality().current_style()
        except Exception:
            return None

    @staticmethod
    def _short_term() -> Optional[Dict]:
        try:
            from memory.short_term import get_short_term_memory

            return get_short_term_memory().snapshot()
        except Exception:
            return None

    @staticmethod
    def _long_term_count() -> Optional[int]:
        try:
            from memory.long_term import get_long_term_memory

            return len(get_long_term_memory().all_facts())
        except Exception:
            return None

    @staticmethod
    def _known_people() -> Optional[int]:
        try:
            from memory.face_memory import get_face_memory

            return len(get_face_memory().known_people())
        except Exception:
            return None

    @staticmethod
    def _known_places() -> Optional[int]:
        try:
            from memory.place_memory import get_place_memory

            return len(get_place_memory().known_places())
        except Exception:
            return None

    @staticmethod
    def _current_place() -> Optional[str]:
        try:
            from memory.place_memory import get_place_memory

            return get_place_memory().current_place()
        except Exception:
            return None

    @staticmethod
    def _detected_habits() -> Optional[int]:
        try:
            from memory.habit_memory import get_habit_memory

            return len(get_habit_memory().detected_habits())
        except Exception:
            return None

    @staticmethod
    def _mood_trend() -> Optional[Dict]:
        try:
            from memory.emotional_memory import EmotionalMemory

            return EmotionalMemory().mood_trend(days=3)
        except Exception:
            return None


_dashboard: Optional[Dashboard] = None


def get_dashboard() -> Dashboard:
    global _dashboard
    if _dashboard is None:
        _dashboard = Dashboard()
    return _dashboard
