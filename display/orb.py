"""
Orb
===
No graphics/game engine lives in this project, so this module doesn't
draw anything - it computes the small state dict a UI layer (a future
desktop overlay, a phone widget, whatever) would need to render one:
color, pulse_rate, and a short label. Same split live_camera.py draws
between "producing" and "using" a frame, one layer up: this produces
orb *state*, it doesn't consume it.

State is derived from two existing sources, never invented here:
CORE.consciousness.reflect() for what Ultron is currently doing
(idle/listening/thinking/speaking, whatever keys that module reports),
and memory/emotional_memory.py's mood_trend() for color warmth -
dashboard.py and reports.py already read both of these; this module
just maps them onto a visual instead of a status string. If either
source is unavailable, the corresponding piece of state falls back to
a fixed neutral default rather than omitting the key - unlike
dashboard.py's snapshot(), a UI needs *some* color/rate every frame,
it can't skip rendering a field.
"""

from typing import Dict, Optional

DEFAULT_COLOR = "#4a9eff"  # neutral blue
DEFAULT_PULSE_RATE = 1.0  # relative speed, 1.0 = resting
DEFAULT_LABEL = "idle"

MOOD_COLORS = {
    "positive": "#4ade80",
    "neutral": "#4a9eff",
    "negative": "#f87171",
}

STATE_PULSE_RATES = {
    "idle": 1.0,
    "listening": 1.4,
    "thinking": 1.8,
    "speaking": 1.6,
}


class Orb:
    """Computes visual-state (not pixels) for a status orb. Use get_orb()."""

    def state(self) -> Dict:
        activity = self._activity_label()
        mood = self._mood_trend()

        color = MOOD_COLORS.get(mood.get("trend") if mood else None, DEFAULT_COLOR)
        pulse_rate = STATE_PULSE_RATES.get(activity, DEFAULT_PULSE_RATE)

        return {"color": color, "pulse_rate": pulse_rate, "label": activity or DEFAULT_LABEL}

    @staticmethod
    def _activity_label() -> Optional[str]:
        try:
            from core.consciousness_p18 import get_consciousness

            reflection = get_consciousness().reflect()
            return reflection.get("activity") or reflection.get("state")
        except Exception:
            return None

    @staticmethod
    def _mood_trend() -> Optional[Dict]:
        try:
            from memory.emotional_memory import EmotionalMemory

            return EmotionalMemory().mood_trend(days=3)
        except Exception:
            return None


_orb: Optional[Orb] = None


def get_orb() -> Orb:
    global _orb
    if _orb is None:
        _orb = Orb()
    return _orb
