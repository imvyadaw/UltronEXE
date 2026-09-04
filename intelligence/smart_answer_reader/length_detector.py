"""
Length Detector (Phase 19.9 - Smart Answer Reader)
==================================================
Classifies a generated answer as short/medium/long/very_long from its
word count, and separately flags whether it has structure (code
fences, tables, bullet/numbered lists, markdown headers) that a
straight text-to-speech read would mangle. Deliberately simple/
heuristic, same spirit as risk_assessor.py in Phase 19.8: a handful
of thresholds and regexes cover the common cases, nothing fancier.

This module only classifies - it never decides what to actually do
about the length (adaptive_formatter.py's job) or extracts anything
from the text (point_extractor.py's job). Stateless: no persistence,
same as relation_mapper.py in Phase 19.7.
"""

import re
import threading
from typing import Dict, Optional

_instance: Optional["LengthDetector"] = None
_instance_lock = threading.Lock()

TIER_SHORT = "short"
TIER_MEDIUM = "medium"
TIER_LONG = "long"
TIER_VERY_LONG = "very_long"

# word-count ceiling for each tier - anything above LONG's ceiling is
# very_long. Chosen for spoken answers, not read answers: ~40 words
# is a couple of sentences, ~120 is a short paragraph, ~300 is
# already a lot to sit through out loud.
_TIER_CEILINGS = {
    TIER_SHORT: 40,
    TIER_MEDIUM: 120,
    TIER_LONG: 300,
}
_TIER_ORDER = [TIER_SHORT, TIER_MEDIUM, TIER_LONG, TIER_VERY_LONG]

# a recommendation is just a hint for adaptive_formatter.py - it
# still makes the final call per output mode
_RECOMMEND_READ_FULL = "read_full"
_RECOMMEND_SUMMARIZE_FIRST = "summarize_first"

_CODE_FENCE_RE = re.compile(r"```")
_TABLE_ROW_RE = re.compile(r"^\s*\|.+\|\s*$", re.MULTILINE)
_BULLET_RE = re.compile(r"^\s*[-*+]\s+\S", re.MULTILINE)
_NUMBERED_RE = re.compile(r"^\s*\d+[.)]\s+\S", re.MULTILINE)
_HEADER_RE = re.compile(r"^\s*#{1,6}\s+\S", re.MULTILINE)


class LengthDetector:
    """answer text -> {"length_tier", "word_count", "char_count",
    "structure_flags", "recommendation", "reasons"}."""

    def detect(self, text: str) -> Dict:
        text = text or ""
        reasons = []

        word_count = len(text.split())
        char_count = len(text)
        tier = self._classify_tier(word_count, reasons)
        structure_flags = self._detect_structure(text, reasons)

        recommendation = _RECOMMEND_READ_FULL
        if tier in (TIER_LONG, TIER_VERY_LONG) or structure_flags["has_code"] or structure_flags["has_table"]:
            recommendation = _RECOMMEND_SUMMARIZE_FIRST
            reasons.append(f"recommending {_RECOMMEND_SUMMARIZE_FIRST}")
        else:
            reasons.append(f"recommending {_RECOMMEND_READ_FULL}")

        return {
            "length_tier": tier,
            "word_count": word_count,
            "char_count": char_count,
            "structure_flags": structure_flags,
            "recommendation": recommendation,
            "reasons": reasons,
        }

    @staticmethod
    def _classify_tier(word_count: int, reasons) -> str:
        for tier in (TIER_SHORT, TIER_MEDIUM, TIER_LONG):
            if word_count <= _TIER_CEILINGS[tier]:
                reasons.append(f"{word_count} words <= {tier} ceiling ({_TIER_CEILINGS[tier]})")
                return tier
        reasons.append(f"{word_count} words exceeds long ceiling ({_TIER_CEILINGS[TIER_LONG]}) - very_long")
        return TIER_VERY_LONG

    @staticmethod
    def _detect_structure(text: str, reasons) -> Dict:
        flags = {
            "has_code": bool(_CODE_FENCE_RE.search(text)),
            "has_table": bool(_TABLE_ROW_RE.search(text)),
            "has_bullet_list": bool(_BULLET_RE.search(text)),
            "has_numbered_list": bool(_NUMBERED_RE.search(text)),
            "has_headers": bool(_HEADER_RE.search(text)),
        }
        for name, present in flags.items():
            if present:
                reasons.append(f"structure flag {name}")
        flags["has_any_structure"] = any(flags.values())
        return flags

    @staticmethod
    def is_more_structured_than(tier_a: str, tier_b: str) -> bool:
        """True if tier_a ranks above tier_b in the short..very_long
        order - a small helper other modules use instead of each
        re-implementing the tier ordering."""
        try:
            return _TIER_ORDER.index(tier_a) > _TIER_ORDER.index(tier_b)
        except ValueError:
            return False


def get_length_detector() -> LengthDetector:
    """Process-wide LengthDetector singleton (stateless, shared for consistency)."""
    global _instance
    if _instance is None:
        with _instance_lock:
            if _instance is None:
                _instance = LengthDetector()
    return _instance
