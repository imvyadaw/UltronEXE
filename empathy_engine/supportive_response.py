"""
Supportive response generator
================================
Turns an emotion_simulator.py posture into an empathetic reply
OPENER (one or two sentences) in the existing bilingual "bhai" voice -
a starting line the rest of the response continues after, not a full
reply on its own.

DELIBERATE SCOPE LIMIT: this module stays firmly in "considerate
assistant" territory, not "therapist" territory - no diagnosis
language, no clinical terms, no crisis-intervention scripting. If a
message signals something more serious than everyday stress/sadness/
frustration, generate_supportive_reply() still returns a caring,
plain-language line, but callers handling genuinely concerning input
should route to a real support resource rather than relying on this
module for that - it deliberately doesn't try to be that.

Uses core.personality.get_personality()'s live "warmth" trait to pick
between a warmer or a more neutral phrasing of the same posture,
same "read the current trait profile, don't hardcode a fixed voice"
approach as advanced_personality/humor_engine.py.
"""

import random
from typing import Dict, Optional

_OPENERS = {
    "celebrate_with": [
        "That's great to hear, bhai!",
        "Love that energy - let's keep it going.",
        "Nice, that's genuinely good news.",
    ],
    "de_escalate": [
        "Samajh raha hoon, bhai - let's take this one step at a time.",
        "I hear you. Let's slow down and sort this out together.",
        "That sounds frustrating. Let's figure out what actually helps right now.",
    ],
    "comfort": [
        "That sounds tough, bhai. I'm here.",
        "I'm sorry you're going through that.",
        "That's a lot to carry - take your time.",
    ],
    "give_space": [
        "Okay, I hear you.",
        "Got it - I'm here whenever you want to talk more.",
    ],
    "neutral": [
        "Got it.",
        "Okay, bhai.",
    ],
}

_WARM_SUFFIX = {
    "comfort": " Let me know if there's anything I can actually do to help.",
    "de_escalate": " Tell me what's going on and we'll work through it.",
}


def generate_supportive_reply(
    posture: Optional[str] = None, emotion: Optional[str] = None, text: Optional[str] = None
) -> Dict:
    """Pass an already-computed `posture` (from
    empathy_engine.emotion_simulator.simulate_emotional_state), OR
    `emotion`/`text` to have it computed here first. Returns
    {"opener": str, "posture": str}."""
    if not posture:
        from empathy_engine.emotion_simulator import simulate_emotional_state

        state = simulate_emotional_state(emotion=emotion, text=text)
        posture = state["posture"]

    posture = posture if posture in _OPENERS else "neutral"
    opener = random.choice(_OPENERS[posture])

    try:
        from core.personality import get_personality

        warmth = get_personality().traits.get("warmth", 0.6)
    except Exception:
        warmth = 0.6

    if warmth > 0.6 and posture in _WARM_SUFFIX:
        opener += _WARM_SUFFIX[posture]

    return {"opener": opener, "posture": posture}
