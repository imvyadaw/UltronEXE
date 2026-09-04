"""
Emotional Tone (Phase 20 - Conversation Layer)
==================================================
Reads a rough emotional tone off the user's text (frustrated, urgent,
happy, confused, or neutral) from surface cues - punctuation,
capitalization, and a handful of keyword lists per tone - and maps
that to a recommended tone for the assistant's own response, so
conversation_engine.py can pass something like "calm_reassuring" or
"concise_direct" downstream instead of every reply defaulting to the
same neutral register regardless of how the user actually sounds.

Deliberately simple/heuristic, same spirit as risk_assessor.py in
Phase 19.8: keyword lists plus a couple of surface signals (ALL CAPS
words, repeated punctuation like "?!" or "!!!") cover the common
cases; nothing here is sentiment analysis in any serious sense, and
an unmatched text defaults to neutral rather than guessing.

Stateless: no persistence, same as relation_mapper.py in Phase 19.7.
This module only classifies tone and recommends a response tone - it
never decides how to phrase anything (that's downstream of
conversation_engine.py) or picks actual filler wording
(filler_generator.py's job, which can take this module's tone as an
input).
"""

import re
import threading
from typing import Dict, List, Optional

_instance: Optional["EmotionalTone"] = None
_instance_lock = threading.Lock()

TONE_NEUTRAL = "neutral"
TONE_FRUSTRATED = "frustrated"
TONE_URGENT = "urgent"
TONE_HAPPY = "happy"
TONE_CONFUSED = "confused"

_RECOMMENDED_RESPONSE_TONE = {
    TONE_NEUTRAL: "neutral",
    TONE_FRUSTRATED: "calm_reassuring",
    TONE_URGENT: "concise_direct",
    TONE_HAPPY: "warm_casual",
    TONE_CONFUSED: "clarifying_patient",
}

_FRUSTRATED_KEYWORDS = {
    "ugh",
    "annoying",
    "frustrated",
    "frustrating",
    "not working",
    "still broken",
    "again?",
    "seriously",
    "come on",
    "this is ridiculous",
    "sick of",
    "fed up",
}
_URGENT_KEYWORDS = {
    "asap",
    "urgent",
    "right now",
    "immediately",
    "hurry",
    "quickly",
    "emergency",
    "as soon as possible",
    "need this now",
}
_HAPPY_KEYWORDS = {
    "thanks",
    "thank you",
    "awesome",
    "great",
    "love it",
    "perfect",
    "nice one",
    "appreciate it",
    "amazing",
    "you're the best",
}
_CONFUSED_KEYWORDS = {
    "don't understand",
    "not sure what",
    "confused",
    "what do you mean",
    "i'm lost",
    "unclear",
    "what does that mean",
    "huh",
}

_ALL_CAPS_WORD_RE = re.compile(r"\b[A-Z]{3,}\b")
_REPEATED_PUNCT_RE = re.compile(r"[!?]{2,}")


class EmotionalTone:
    """text -> {"tone", "confidence", "signals"}; recommend_response_tone(tone) -> str."""

    def detect(self, text: str) -> Dict:
        text = text or ""
        lowered = text.lower()
        signals: List[str] = []
        scores = {TONE_FRUSTRATED: 0.0, TONE_URGENT: 0.0, TONE_HAPPY: 0.0, TONE_CONFUSED: 0.0}

        for keyword in _FRUSTRATED_KEYWORDS:
            if keyword in lowered:
                scores[TONE_FRUSTRATED] += 0.3
                signals.append(f"frustrated keyword '{keyword}'")
        for keyword in _URGENT_KEYWORDS:
            if keyword in lowered:
                scores[TONE_URGENT] += 0.3
                signals.append(f"urgent keyword '{keyword}'")
        for keyword in _HAPPY_KEYWORDS:
            if keyword in lowered:
                scores[TONE_HAPPY] += 0.3
                signals.append(f"happy keyword '{keyword}'")
        for keyword in _CONFUSED_KEYWORDS:
            if keyword in lowered:
                scores[TONE_CONFUSED] += 0.3
                signals.append(f"confused keyword '{keyword}'")

        if _ALL_CAPS_WORD_RE.search(text):
            scores[TONE_FRUSTRATED] += 0.2
            scores[TONE_URGENT] += 0.15
            signals.append("contains an ALL-CAPS word")

        if _REPEATED_PUNCT_RE.search(text):
            scores[TONE_FRUSTRATED] += 0.15
            scores[TONE_URGENT] += 0.15
            signals.append("repeated punctuation ('!!' / '?!')")

        best_tone = max(scores, key=scores.get)
        best_score = scores[best_tone]
        if best_score <= 0.0:
            return {"tone": TONE_NEUTRAL, "confidence": 0.5, "signals": ["no strong tone cues found"]}

        confidence = min(1.0, 0.4 + best_score)
        return {"tone": best_tone, "confidence": round(confidence, 3), "signals": signals}

    @staticmethod
    def recommend_response_tone(tone: str) -> str:
        return _RECOMMENDED_RESPONSE_TONE.get(tone, "neutral")


def get_emotional_tone() -> EmotionalTone:
    """Process-wide EmotionalTone singleton (stateless, shared for consistency)."""
    global _instance
    if _instance is None:
        with _instance_lock:
            if _instance is None:
                _instance = EmotionalTone()
    return _instance
