"""
Tone manager
============
Picks a line from ultron_phrases.py's bank for a given category, avoids
repeating the same line twice in a row per category, and safely fills
in the `{percent}` / `{name}` / `{title}` / `{minutes}` placeholders
without raising if a kwarg is missing (a proactive alert firing is not
the place for a KeyError to take down the engine loop).

Tone (`Tone.CASUAL` / `FORMAL` / `URGENT`) doesn't currently select a
different line bank - the phrase bank is written in one consistent
ULTRON voice - but it does control *delivery*: urgent alerts skip any
"by the way" softening and are marked for ui.notifications.notify() as
level="warning"/"error" and for the voice layer to interrupt rather
than queue. Kept as an explicit enum (not a bare string) so callers get
autocomplete/typo-safety, and so a future "different phrasing per tone"
upgrade doesn't need to change every call site.
"""

import random
from enum import Enum
from typing import Dict, Optional

from proactive.personality.ultron_phrases import get_phrases

# Categories severe enough that, regardless of caller intent, delivery
# should be urgent (interrupt/notify loudly) rather than casually queued.
_URGENT_CATEGORIES = {"battery_critical", "meeting_starting"}
_WARNING_CATEGORIES = {"cpu_high", "memory_high", "disk_high", "battery_low", "network_down", "general_concern"}


class Tone(str, Enum):
    CASUAL = "casual"
    FORMAL = "formal"
    URGENT = "urgent"


class _SafeDict(dict):
    """Passed to str.format_map so a template referencing a kwarg the
    caller didn't supply renders as literal `{that_key}` instead of
    raising KeyError - a missing placeholder shouldn't crash an alert."""

    def __missing__(self, key):
        return "{" + key + "}"


def _notification_level_for(category: str, tone: Tone) -> str:
    if tone == Tone.URGENT or category in _URGENT_CATEGORIES:
        return "error"
    if category in _WARNING_CATEGORIES:
        return "warning"
    return "info"


class ToneManager:
    """Stateful phrase picker: one instance per process, remembers the
    last line used per category so the same wisecrack doesn't repeat
    back-to-back."""

    def __init__(self):
        self._last_used: Dict[str, str] = {}

    def infer_tone(self, category: str) -> Tone:
        if category in _URGENT_CATEGORIES:
            return Tone.URGENT
        if category in _WARNING_CATEGORIES:
            return Tone.CASUAL
        return Tone.CASUAL

    def get_phrase(self, category: str, tone: Optional[Tone] = None, **kwargs) -> Dict:
        """Returns {"text": <formatted line>, "tone": Tone, "level": "info"/"warning"/"error"}.
        If the category is unknown, falls back to a plain, honest sentence
        built from kwargs rather than silently returning nothing."""
        templates = get_phrases(category)
        tone = tone or self.infer_tone(category)

        if not templates:
            fallback = kwargs.get("message") or category.replace("_", " ")
            text = f"Sir, {fallback}."
        else:
            choice = random.choice(templates)
            # Avoid repeating the exact same line as last time for this
            # category, when there's more than one option to pick from.
            if len(templates) > 1 and choice == self._last_used.get(category):
                remaining = [t for t in templates if t != choice]
                choice = random.choice(remaining)
            self._last_used[category] = choice
            text = choice.format_map(_SafeDict(**kwargs))

        return {
            "text": text,
            "tone": tone.value,
            "level": _notification_level_for(category, tone),
            "category": category,
        }


_manager: Optional[ToneManager] = None


def get_tone_manager() -> ToneManager:
    global _manager
    if _manager is None:
        _manager = ToneManager()
    return _manager
