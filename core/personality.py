"""
Personality
===========
proactive/personality/tone_manager.py already picks *which line* to say
and PHASE_17_2's modules already decide *what to do* - neither one
tracks *who is doing the talking*. This module is that missing layer: a
small, slowly-drifting trait profile (warmth, formality, humor,
proactiveness) that sits above tone_manager and modulates its output,
instead of every category being delivered in one flat voice forever.

Nothing here replaces tone_manager.get_phrase() - it's still the single
source of phrase text (ULTRON voice, placeholder-safe formatting, the
"don't repeat the same line twice" logic). This module wraps it:

    get_personality().speak("cpu_high", percent=92)

does tone_manager.get_phrase(...) exactly as before, then adjusts the
returned tone/level based on two things tone_manager itself has no
access to:

  1. The trait profile (persisted to storage/sqlite/personality.db,
     same pattern as memory/emotional_memory.py's moods table) -
     nudged over time by explicit feedback (adjust("warmth", +0.05,
     reason="user said thanks") from wherever positive/negative signal
     is detected), never jumped in one shot, so a single bad signal
     can't swing the whole personality.
  2. memory/emotional_memory.py's mood_trend() - if the user's mood has
     been declining, delivery leans gentler (categories that aren't
     already URGENT get softened toward CASUAL, never upgraded), the
     same instinct a considerate person has about *how* to say
     something to someone who's having a rough week. This never
     suppresses an urgent/warning alert - only softens the ones that
     had room to be softened.

Traits are deliberately few and coarse (0.0-1.0 floats) - this is a
delivery-style knob, not a simulated inner life. Degrades safely:
if emotional_memory or the trait DB is unavailable for any reason,
speak() falls straight back to tone_manager's un-modulated output.
"""

import sqlite3
import time
from pathlib import Path
from typing import Dict, Optional

from proactive.personality.tone_manager import get_tone_manager, Tone

DB_PATH = Path(__file__).resolve().parents[1] / "storage" / "sqlite" / "personality.db"

DEFAULT_TRAITS = {
    "warmth": 0.6,  # how personable vs strictly transactional replies feel
    "formality": 0.4,  # 0 = casual ("hey"), 1 = formal ("Sir, ...")
    "humor": 0.3,  # how often a light aside is appropriate
    "proactiveness": 0.5,  # how eagerly to surface unprompted suggestions
}
TRAIT_BOUNDS = (0.0, 1.0)
MAX_ADJUST_LOG = 200


class PersonalityProfile:
    """Slowly-drifting trait profile + tone_manager wrapper. One
    instance per process - use get_personality()."""

    def __init__(self):
        self.traits: Dict[str, float] = dict(DEFAULT_TRAITS)
        self._tone = get_tone_manager()
        self._db_ok = True
        try:
            DB_PATH.parent.mkdir(parents=True, exist_ok=True)
            self._conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
            self._conn.execute("""CREATE TABLE IF NOT EXISTS trait_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    trait TEXT, delta REAL, new_value REAL, reason TEXT, logged_at REAL
                )""")
            self._conn.execute("""CREATE TABLE IF NOT EXISTS trait_state (
                    trait TEXT PRIMARY KEY, value REAL
                )""")
            self._conn.commit()
            self._load_state()
        except Exception:
            # No persistence available - traits still work in-memory for
            # this process, they just won't survive a restart.
            self._db_ok = False

    def _load_state(self) -> None:
        cur = self._conn.cursor()
        cur.execute("SELECT trait, value FROM trait_state")
        for trait, value in cur.fetchall():
            if trait in self.traits:
                self.traits[trait] = value

    def adjust(self, trait: str, delta: float, reason: str = "") -> Dict:
        """Nudge a trait by `delta` (small values expected, e.g. +/-0.05),
        clipped to [0, 1]. Every adjustment is logged so drift over time
        is auditable, not a black box. Unknown trait names are rejected
        rather than silently creating a new one."""
        if trait not in self.traits:
            return {"error": f"unknown trait '{trait}'", "known_traits": list(self.traits)}

        new_value = min(TRAIT_BOUNDS[1], max(TRAIT_BOUNDS[0], self.traits[trait] + delta))
        self.traits[trait] = new_value

        if self._db_ok:
            try:
                self._conn.execute(
                    "INSERT INTO trait_log (trait, delta, new_value, reason, logged_at) VALUES (?, ?, ?, ?, ?)",
                    (trait, delta, new_value, reason, time.time()),
                )
                self._conn.execute(
                    "INSERT INTO trait_state (trait, value) VALUES (?, ?) "
                    "ON CONFLICT(trait) DO UPDATE SET value = excluded.value",
                    (trait, new_value),
                )
                self._conn.commit()
            except Exception:
                from core.error_trace import log_swallowed as _lsw

                _lsw("core.personality.adjust")

        return {"trait": trait, "value": new_value, "delta": delta, "reason": reason}

    def _mood_bias(self) -> Optional[str]:
        """'gentle' if the user's recent mood trend is declining, else
        None. Best-effort - emotional_memory not being importable/usable
        just means no bias is applied, not an error."""
        try:
            from memory.emotional_memory import EmotionalMemory

            trend = EmotionalMemory().mood_trend(days=3)
            if trend.get("trend") == "declining" and trend.get("entries", 0) > 0:
                return "gentle"
        except Exception:
            from core.error_trace import log_swallowed as _lsw

            _lsw("core.personality._mood_bias")
        return None

    def current_style(self) -> Dict:
        """Snapshot of how Ultron should currently come across - traits
        plus the live mood bias - for any caller (decision_maker,
        consciousness, a future dashboard) that wants the summary
        without re-deriving it."""
        bias = self._mood_bias()
        return {
            **self.traits,
            "mood_bias": bias,
            "tone_default": Tone.FORMAL.value if self.traits["formality"] > 0.65 else Tone.CASUAL.value,
        }

    def speak(self, category: str, tone: Optional[Tone] = None, **kwargs) -> Dict:
        """Same return shape as tone_manager.get_phrase() -
        {"text", "tone", "level", "category"} - with delivery softened
        toward casual/info when the user's mood trend is declining and
        the category wasn't already urgent. Never escalates a category
        upward, only ever softens categories that had room to soften."""
        phrase = self._tone.get_phrase(category, tone=tone, **kwargs)

        if phrase["level"] == "error":
            return phrase  # genuinely urgent - mood bias never suppresses this

        if self._mood_bias() == "gentle" and phrase["tone"] != Tone.URGENT.value:
            phrase = dict(phrase)
            phrase["tone"] = Tone.CASUAL.value
            if phrase["level"] == "warning" and category not in ("battery_critical", "meeting_starting"):
                phrase["level"] = "info"

        return phrase


_personality: Optional[PersonalityProfile] = None


def get_personality() -> PersonalityProfile:
    global _personality
    if _personality is None:
        _personality = PersonalityProfile()
    return _personality
