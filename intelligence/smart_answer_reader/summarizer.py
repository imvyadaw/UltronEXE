"""
Summarizer (Phase 19.9 - Smart Answer Reader)
==================================================
Condenses an answer into running prose at one of three sizes:

    one_liner - a single sentence, for a quick voice reply
    brief     - two to three sentences, the default spoken summary
    detailed  - up to six sentences, for a screen recap of a long answer

Builds the summary out of point_extractor.py's ranked points rather
than re-analyzing the text itself - this module's only job is
picking how many of those points to use for a given style and
stitching them back into original-text order so the result reads
like a paragraph, not a shuffled list. If point_extractor.py finds
nothing usable (e.g. text too short to have real "candidates"), the
original text is returned unchanged rather than an empty string.

Stateless: no persistence, same as skill_generator.py in Phase 19.6.
This module only condenses - it never decides which style a given
answer/output-mode needs (adaptive_formatter.py's job) or extracts
the underlying points itself (point_extractor.py's job).
"""

import threading
from typing import Dict, List, Optional

from intelligence.smart_answer_reader.point_extractor import get_point_extractor

_instance: Optional["Summarizer"] = None
_instance_lock = threading.Lock()

STYLE_ONE_LINER = "one_liner"
STYLE_BRIEF = "brief"
STYLE_DETAILED = "detailed"

# how many points each style pulls in, at most - summarize() also
# caps by the actual number of points point_extractor.py returns
_STYLE_POINT_COUNT = {
    STYLE_ONE_LINER: 1,
    STYLE_BRIEF: 3,
    STYLE_DETAILED: 6,
}


class Summarizer:
    """answer text (+ optional pre-extracted points) -> {"summary",
    "style", "sentence_count", "used_points"}."""

    def __init__(self):
        self._extractor = get_point_extractor()

    def summarize(self, text: str, style: str = STYLE_BRIEF, points: Optional[List[Dict]] = None) -> Dict:
        text = text or ""
        style = style if style in _STYLE_POINT_COUNT else STYLE_BRIEF
        max_points = _STYLE_POINT_COUNT[style]

        if points is None:
            points = self._extractor.extract_in_original_order(text, max_points=max_points)
        else:
            points = sorted(points, key=lambda p: p.get("_order", 0))[:max_points]

        if not points:
            # nothing to condense - text was likely already short/simple
            return {
                "summary": text.strip(),
                "style": style,
                "sentence_count": self._count_sentences(text),
                "used_points": [],
                "fell_back_to_original": True,
            }

        sentences = [self._as_sentence(p["text"]) for p in points]
        summary = " ".join(sentences)
        return {
            "summary": summary,
            "style": style,
            "sentence_count": len(sentences),
            "used_points": points,
            "fell_back_to_original": False,
        }

    def summarize_all_styles(self, text: str) -> Dict[str, Dict]:
        """Convenience for callers (answer_reader_engine.py) that want
        every style up front instead of calling summarize() three
        times - extracts points once at the largest count needed and
        slices down for the shorter styles."""
        widest = self._extractor.extract_in_original_order(text, max_points=_STYLE_POINT_COUNT[STYLE_DETAILED])
        return {
            style: self.summarize(text, style=style, points=widest)
            for style in (STYLE_ONE_LINER, STYLE_BRIEF, STYLE_DETAILED)
        }

    @staticmethod
    def _as_sentence(point_text: str) -> str:
        point_text = point_text.strip()
        if not point_text:
            return point_text
        if point_text[-1] not in ".!?":
            point_text += "."
        return point_text[0].upper() + point_text[1:]

    @staticmethod
    def _count_sentences(text: str) -> int:
        return len([s for s in text.replace("!", ".").replace("?", ".").split(".") if s.strip()])


def get_summarizer() -> Summarizer:
    """Process-wide Summarizer singleton (stateless, shared for consistency)."""
    global _instance
    if _instance is None:
        with _instance_lock:
            if _instance is None:
                _instance = Summarizer()
    return _instance
