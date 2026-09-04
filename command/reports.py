"""
Report Generator
================
history.py answers "what happened, in order"; this module answers "so
what" - periodic digests that turn dashboard.py's snapshot plus
long_term/place data into a short human-readable summary (mood trend,
recurring patterns currently tracked, facts learned, places visited),
delivered through personality.speak() so a report reads in Ultron's
current voice rather than as a bare data dump. Structured data is
always returned alongside the text, since a UI (or a future COMMAND
surface) may want the numbers without the prose.
"""

import time
from typing import Dict, List, Optional

REPORT_WINDOWS = {"daily": 1, "weekly": 7}


class ReportGenerator:
    """Periodic activity digests. Use get_report_generator()."""

    def daily_report(self) -> Dict:
        return self._report("daily")

    def weekly_report(self) -> Dict:
        return self._report("weekly")

    def _report(self, period: str) -> Dict:
        days = REPORT_WINDOWS.get(period, 1)
        cutoff = time.time() - days * 86400

        recent_facts = [f for f in self._all_facts() if f.get("last_seen", 0) >= cutoff]
        recent_places = self._recent_places(cutoff)
        habit_count = self._habit_count()
        mood_trend = self._mood_trend()

        lines = [f"Here's your {period} summary:"]
        lines.append(f"- {len(recent_facts)} new or reinforced fact(s) learned")
        lines.append(f"- {len(recent_places)} place(s) visited")
        lines.append(f"- {habit_count} recurring pattern(s) currently tracked")
        if mood_trend and mood_trend.get("trend"):
            lines.append(f"- mood trend: {mood_trend['trend']}")

        text = self._speak("\n".join(lines))

        return {
            "period": period,
            "since": cutoff,
            "facts_learned": recent_facts,
            "places_visited": recent_places,
            "habit_count": habit_count,
            "mood_trend": mood_trend,
            "text": text,
        }

    @staticmethod
    def _all_facts() -> List[Dict]:
        try:
            from memory.long_term import get_long_term_memory

            return get_long_term_memory().all_facts()
        except Exception:
            return []

    @staticmethod
    def _recent_places(cutoff: float) -> List[str]:
        try:
            from memory.place_memory import get_place_memory

            visits = get_place_memory().place_history(limit=200)
            seen = {v["place"] for v in visits if v["arrived_at"] >= cutoff}
            return sorted(seen)
        except Exception:
            return []

    @staticmethod
    def _habit_count() -> int:
        try:
            from memory.habit_memory import get_habit_memory

            return len(get_habit_memory().detected_habits())
        except Exception:
            return 0

    @staticmethod
    def _mood_trend() -> Optional[Dict]:
        try:
            from memory.emotional_memory import EmotionalMemory

            return EmotionalMemory().mood_trend(days=3)
        except Exception:
            return None

    @staticmethod
    def _speak(summary: str) -> str:
        """Wraps the summary through personality.speak() so it reads
        in Ultron's current voice; falls back to the plain summary if
        personality/tone_manager has no matching phrase category,
        same fallback pattern decision_maker.py uses for its clarify
        question."""
        try:
            from core.personality import get_personality

            phrase = get_personality().speak("general_update", message=summary)
            return phrase.get("text") or summary
        except Exception:
            return summary


_report_generator: Optional[ReportGenerator] = None


def get_report_generator() -> ReportGenerator:
    global _report_generator
    if _report_generator is None:
        _report_generator = ReportGenerator()
    return _report_generator
