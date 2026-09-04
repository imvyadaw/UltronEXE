"""
Adaptive Formatter (Phase 19.9 - Smart Answer Reader)
==================================================
Decides what a user actually sees or hears for a given answer, given
length_detector.py's classification and (when needed) summarizer.py's
condensed versions. This is the module that turns "the answer is
very_long and has a table" into a concrete decision: show the full
text on screen with the key points pinned above it, but only speak
a one-line summary out loud and offer to read the rest.

Two output modes:
    "screen" - the user can read at their own pace, so structure
               (tables/code/lists) is preserved and length is rarely
               a reason to truncate - only summarize_first answers
               get a short "key points" preamble above the full text.
    "voice"  - read out loud by tts_preparer.py's output, so length
               and structure both matter a lot more. short/medium
               answers are read in full; long/very_long answers get
               a brief/one_liner summary plus an offer to hear more,
               since nobody wants a table read aloud sentence by
               sentence.

Mirrors decision_gate.py's role in Phase 19.8 in spirit (the module
that turns several other modules' outputs into one concrete decision)
but doesn't persist anything - formatting choices aren't outcomes to
learn from the way gate decisions are, so there's nothing here for a
future *_learner.py to check against.

Stateless: no persistence. This module only decides what to
show/speak - it never extracts points (point_extractor.py's job),
condenses text (summarizer.py's job), or cleans text for TTS
(tts_preparer.py's job).
"""

import threading
from typing import Dict, List, Optional

from intelligence.smart_answer_reader.length_detector import (
    TIER_SHORT,
    TIER_MEDIUM,
    TIER_LONG,
    TIER_VERY_LONG,
)
from intelligence.smart_answer_reader.summarizer import STYLE_ONE_LINER, STYLE_BRIEF, STYLE_DETAILED

_instance: Optional["AdaptiveFormatter"] = None
_instance_lock = threading.Lock()

MODE_VOICE = "voice"
MODE_SCREEN = "screen"

# per (mode, length_tier): which summary style to lead with, or None
# to just use the full original text as-is
_VOICE_STYLE_BY_TIER = {
    TIER_SHORT: None,
    TIER_MEDIUM: None,
    TIER_LONG: STYLE_BRIEF,
    TIER_VERY_LONG: STYLE_ONE_LINER,
}
_SCREEN_STYLE_BY_TIER = {
    TIER_SHORT: None,
    TIER_MEDIUM: None,
    TIER_LONG: STYLE_DETAILED,
    TIER_VERY_LONG: STYLE_DETAILED,
}


class AdaptiveFormatter:
    """(text, length_info, mode, summaries_by_style) -> {"mode",
    "length_tier", "primary_text", "key_points", "offered_expansion",
    "expansion_hint"}."""

    def format_answer(
        self,
        text: str,
        length_info: Dict,
        mode: str = MODE_VOICE,
        summaries_by_style: Optional[Dict[str, Dict]] = None,
        points: Optional[List[Dict]] = None,
    ) -> Dict:
        text = text or ""
        mode = mode if mode in (MODE_VOICE, MODE_SCREEN) else MODE_VOICE
        summaries_by_style = summaries_by_style or {}
        tier = length_info.get("length_tier", TIER_SHORT)
        structure = length_info.get("structure_flags", {})

        if mode == MODE_VOICE:
            return self._format_for_voice(text, tier, structure, summaries_by_style)
        return self._format_for_screen(text, tier, structure, summaries_by_style, points)

    @staticmethod
    def _format_for_voice(text: str, tier: str, structure: Dict, summaries_by_style: Dict) -> Dict:
        style = _VOICE_STYLE_BY_TIER.get(tier)
        needs_structure_summary = structure.get("has_code") or structure.get("has_table")
        if needs_structure_summary and style is None:
            style = STYLE_BRIEF  # a short answer that's still a code block/table shouldn't be read raw

        if style is None:
            return {
                "mode": MODE_VOICE,
                "length_tier": tier,
                "primary_text": text.strip(),
                "key_points": [],
                "offered_expansion": False,
                "expansion_hint": None,
            }

        summary = summaries_by_style.get(style) or {"summary": text.strip(), "fell_back_to_original": True}
        return {
            "mode": MODE_VOICE,
            "length_tier": tier,
            "primary_text": summary["summary"],
            "key_points": [],
            "offered_expansion": True,
            "expansion_hint": "Want me to read the full answer?",
        }

    @staticmethod
    def _format_for_screen(
        text: str, tier: str, structure: Dict, summaries_by_style: Dict, points: Optional[List[Dict]]
    ) -> Dict:
        style = _SCREEN_STYLE_BY_TIER.get(tier)
        if style is None:
            return {
                "mode": MODE_SCREEN,
                "length_tier": tier,
                "primary_text": text.strip(),
                "key_points": [],
                "offered_expansion": False,
                "expansion_hint": None,
            }

        key_points = [p["text"] for p in (points or [])]
        return {
            "mode": MODE_SCREEN,
            "length_tier": tier,
            "primary_text": text.strip(),
            "key_points": key_points,
            "offered_expansion": False,
            "expansion_hint": None,
        }


def get_adaptive_formatter() -> AdaptiveFormatter:
    """Process-wide AdaptiveFormatter singleton (stateless, shared for consistency)."""
    global _instance
    if _instance is None:
        with _instance_lock:
            if _instance is None:
                _instance = AdaptiveFormatter()
    return _instance
