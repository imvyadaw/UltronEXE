"""
Continuity Tracker (Phase 20 - Conversation Layer)
==================================================
Given the previous turn's text and the current one (plus how long the
gap between them was), estimates whether the current turn continues
the same topic or is a fresh start - and flags leading pronouns/
references ("it", "that", "them") that only make sense if it's a
continuation. conversation_engine.py uses this to decide, among other
things, how much prior context a downstream reasoning step should
carry forward.

Scoring is a handful of additive/subtractive heuristics, same spirit
as confidence_calculator.py's weighted signals in Phase 19.8: word
overlap between the two turns pulls the shift score down (more
overlap = more likely a continuation), an explicit topic-change cue
("by the way", "anyway", "unrelated question") pushes it up, a long
gap between turns pushes it up, and a leading pronoun/reference pulls
it down. Nothing here is a hard cutoff - topic_shift_score is a
continuous [0, 1] value and is_continuation is just that score
thresholded at 0.5, so callers that want their own cutoff can use the
raw score directly.

Stateless: no persistence, same as entity_extractor.py in Phase 19.7.
This module only measures continuity between two given turns - it
never fetches turn history itself (turn_manager.py's job) or decides
what to do with the result (conversation_engine.py's job).
"""

import re
import threading
from typing import Dict, List, Optional, Set

_instance: Optional["ContinuityTracker"] = None
_instance_lock = threading.Lock()

_WORD_RE = re.compile(r"[a-z0-9']+")

# generic words that overlapping on their own says nothing about topic
_STOPWORDS = {
    "the",
    "a",
    "an",
    "is",
    "are",
    "was",
    "were",
    "be",
    "been",
    "to",
    "of",
    "in",
    "on",
    "for",
    "and",
    "or",
    "but",
    "with",
    "that",
    "this",
    "it",
    "i",
    "you",
    "we",
    "they",
    "do",
    "does",
    "did",
    "can",
    "could",
    "would",
    "should",
    "will",
    "my",
    "your",
    "so",
}

_LEADING_REFERENCE_WORDS = {"it", "that", "this", "them", "those", "these", "he", "she", "they"}

_TOPIC_SHIFT_CUES = {
    "by the way",
    "anyway",
    "unrelated question",
    "different topic",
    "changing topic",
    "new question",
    "on another note",
    "switching gears",
    "forget that",
}
_TOPIC_CONTINUE_CUES = {"also", "and also", "additionally", "furthermore", "on that note", "following up"}

# a gap this long between turns starts to look like a resumed session
# rather than a continuous exchange
_LONG_GAP_SECONDS = 120.0

_WEIGHT_OVERLAP = 0.40
_WEIGHT_GAP = 0.20
_WEIGHT_SHIFT_CUE = 0.30
_WEIGHT_REFERENCE = 0.25
_WEIGHT_CONTINUE_CUE = 0.20


class ContinuityTracker:
    """(previous_text, current_text, gap_seconds) -> {"is_continuation",
    "topic_shift_score", "has_reference", "reasons"}."""

    def analyze(self, previous_text: Optional[str], current_text: str, gap_seconds: float = 0.0) -> Dict:
        current_text = current_text or ""
        reasons: List[str] = []

        if not previous_text:
            reasons.append("no previous turn to compare against - treating as a fresh start")
            return {"is_continuation": False, "topic_shift_score": 1.0, "has_reference": False, "reasons": reasons}

        shift_score = 0.5  # start neutral, nudge from there
        prev_words = self._content_words(previous_text)
        curr_words = self._content_words(current_text)

        overlap_ratio = self._overlap_ratio(prev_words, curr_words)
        shift_score -= overlap_ratio * _WEIGHT_OVERLAP
        reasons.append(f"content-word overlap ratio {overlap_ratio:.2f}")

        if gap_seconds >= _LONG_GAP_SECONDS:
            shift_score += _WEIGHT_GAP
            reasons.append(f"gap of {gap_seconds:.0f}s is long enough to suggest a resumed session")

        lowered_curr = current_text.lower()
        if any(cue in lowered_curr for cue in _TOPIC_SHIFT_CUES):
            shift_score += _WEIGHT_SHIFT_CUE
            reasons.append("matched an explicit topic-shift cue")
        if any(cue in lowered_curr for cue in _TOPIC_CONTINUE_CUES):
            shift_score -= _WEIGHT_CONTINUE_CUE
            reasons.append("matched an explicit topic-continuation cue")

        has_reference = self._starts_with_reference(current_text)
        if has_reference:
            shift_score -= _WEIGHT_REFERENCE
            reasons.append("current turn opens with a pronoun/reference that implies continuation")

        shift_score = max(0.0, min(1.0, shift_score))
        is_continuation = shift_score < 0.5
        return {
            "is_continuation": is_continuation,
            "topic_shift_score": round(shift_score, 3),
            "has_reference": has_reference,
            "reasons": reasons,
        }

    @staticmethod
    def _content_words(text: str) -> Set[str]:
        words = _WORD_RE.findall(text.lower())
        return {w for w in words if w not in _STOPWORDS}

    @staticmethod
    def _overlap_ratio(a: Set[str], b: Set[str]) -> float:
        if not a or not b:
            return 0.0
        intersection = a & b
        smaller = min(len(a), len(b))
        return len(intersection) / smaller if smaller else 0.0

    @staticmethod
    def _starts_with_reference(text: str) -> bool:
        words = _WORD_RE.findall(text.lower())
        return bool(words) and words[0] in _LEADING_REFERENCE_WORDS


def get_continuity_tracker() -> ContinuityTracker:
    """Process-wide ContinuityTracker singleton (stateless, shared for consistency)."""
    global _instance
    if _instance is None:
        with _instance_lock:
            if _instance is None:
                _instance = ContinuityTracker()
    return _instance
