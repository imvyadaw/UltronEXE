"""
Sarcasm detector
==================
Same design philosophy as voice/emotion_detection.py's
analyze_text_sentiment(): a fast, offline, keyword/pattern heuristic,
explicitly NOT a trained classifier - sarcasm is genuinely hard to
detect from text alone even for humans, so this is a "mood hint at
most", same caution that module's own docstring states, never a basis
for a consequential decision about the user.

Signals combined (each contributes a small score, nothing alone is
decisive):
  - a positive-sentiment word appearing right next to strong negative
    punctuation/emphasis ("great..." / "great!!" / "wow really") -
    the classic mismatch-between-words-and-emphasis pattern.
  - known sarcasm markers ("yeah right", "sure sure", "oh great",
    "as if", "totally", "wow thanks for that").
  - a quoted word immediately after a positive word ("so \"helpful\"") -
    scare-quoting a compliment is a strong sarcasm tell.
  - excessive punctuation repetition ("!!!", "???", "..") paired with
    an otherwise-short message, which plain enthusiasm rarely needs.
"""

import re
from typing import Dict

_MARKER_PHRASES = [
    "yeah right",
    "sure sure",
    "oh great",
    "oh wonderful",
    "as if",
    "totally",
    "wow thanks",
    "thanks a lot",
    "nice job",
    "great job",
    "just great",
    "how original",
    "what a surprise",
    "shocking, i know",
]
_POSITIVE_WORDS = {
    "great",
    "wonderful",
    "perfect",
    "love",
    "amazing",
    "fantastic",
    "brilliant",
    "genius",
    "lovely",
    "nice",
    "awesome",
}
_SCARE_QUOTE_RE = re.compile(r'"[^"]{1,20}"')
_REPEAT_PUNCT_RE = re.compile(r"([!?.])\1{1,}")


def detect_sarcasm(text: str) -> Dict:
    """Returns {"is_sarcastic": bool, "confidence": float (0-1),
    "signals": [str, ...]}. Confidence is a rough heuristic sum, not a
    calibrated probability - use it to gate tone, not to make a firm
    claim about the user's intent."""
    if not text or not text.strip():
        return {"is_sarcastic": False, "confidence": 0.0, "signals": []}

    lower = text.lower()
    words = set(re.findall(r"[a-z']+", lower))
    signals = []
    score = 0.0

    for phrase in _MARKER_PHRASES:
        if phrase in lower:
            signals.append(f"marker phrase: '{phrase}'")
            score += 0.4

    positive_hits = words & _POSITIVE_WORDS
    if positive_hits and _REPEAT_PUNCT_RE.search(text):
        signals.append("positive word + repeated punctuation")
        score += 0.3

    if positive_hits and _SCARE_QUOTE_RE.search(text):
        signals.append("positive word near a scare-quoted phrase")
        score += 0.3

    if positive_hits and re.search(r"\b(really|wow|oh)\b", lower):
        signals.append("positive word + hedging exclamation ('wow'/'really'/'oh')")
        score += 0.2

    confidence = min(1.0, round(score, 2))
    return {"is_sarcastic": confidence >= 0.4, "confidence": confidence, "signals": signals}
