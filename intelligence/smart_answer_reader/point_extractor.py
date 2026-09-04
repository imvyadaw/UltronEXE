"""
Point Extractor (Phase 19.9 - Smart Answer Reader)
==================================================
Pulls the sentences/list-items that best represent an answer's
content out of the full text, each with a heuristic importance
score. Used when length_detector.py recommends summarize_first -
summarizer.py condenses these points into prose, and
adaptive_formatter.py can show them as a scannable list on screen.

Scoring is a handful of additive heuristics, same spirit as
confidence_calculator.py's weighted signals in Phase 19.8: existing
bullet/numbered list items start with a strong boost (the answer
already told us these are the key items), the first sentence of each
paragraph gets a smaller one (topic sentences), sentences containing
a number/stat get a bump (concrete facts read well as key points),
and a short cue-word list ("important", "note", "key", "must",
"should", "critical", "warning") adds a little more. Everything else
is scored on cue words and position alone. Extremely short (<4 words)
or extremely long (>60 words) sentences are penalized rather than
dropped outright, since a caller who asks for more points than the
penalty-free candidates can supply should still get something back.

Stateless: no persistence, same as entity_extractor.py in Phase 19.7.
This module only extracts and scores - it never condenses into
running prose (summarizer.py's job) or decides how many points a
given output actually needs (adaptive_formatter.py's job).
"""

import re
import threading
from typing import Dict, List, Optional

_instance: Optional["PointExtractor"] = None
_instance_lock = threading.Lock()

_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\"'(])")
_BULLET_LINE_RE = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+(.*\S)\s*$")
_CODE_FENCE_RE = re.compile(r"```.*?```", re.DOTALL)
_NUMBER_RE = re.compile(r"\d")
_CUE_WORDS = {
    "important",
    "note",
    "key",
    "must",
    "should",
    "critical",
    "warning",
    "essential",
    "crucial",
    "remember",
    "caution",
    "required",
}

_SCORE_LIST_ITEM = 0.45
_SCORE_TOPIC_SENTENCE = 0.20
_SCORE_HAS_NUMBER = 0.15
_SCORE_CUE_WORD = 0.15
_SCORE_FIRST_OVERALL = 0.10
_PENALTY_TOO_SHORT = 0.25
_PENALTY_TOO_LONG = 0.15
_MIN_WORDS = 4
_MAX_WORDS = 60


class PointExtractor:
    """answer text -> ranked list of {"text", "score", "reasons", "source"}."""

    def extract(self, text: str, max_points: int = 5) -> List[Dict]:
        text = text or ""
        stripped = _CODE_FENCE_RE.sub(" ", text)  # code blocks make poor spoken/summary points
        candidates = self._collect_candidates(stripped)
        if not candidates:
            return []

        scored = [self._score(idx, candidate, len(candidates)) for idx, candidate in enumerate(candidates)]
        scored.sort(key=lambda c: c["score"], reverse=True)
        return scored[: max(0, max_points)]

    @staticmethod
    def _collect_candidates(text: str) -> List[Dict]:
        """Each candidate is a {"text", "is_list_item", "is_topic_sentence",
        "position"} dict, built paragraph by paragraph so topic-sentence
        and position scoring stay meaningful."""
        candidates: List[Dict] = []
        paragraphs = [p for p in re.split(r"\n\s*\n", text) if p.strip()]
        for paragraph in paragraphs:
            lines = [ln for ln in paragraph.split("\n") if ln.strip()]
            first_sentence_seen = False
            for line in lines:
                bullet_match = _BULLET_LINE_RE.match(line)
                if bullet_match:
                    candidates.append(
                        {
                            "text": bullet_match.group(1).strip(),
                            "is_list_item": True,
                            "is_topic_sentence": False,
                        }
                    )
                    continue
                for sentence in _SENTENCE_SPLIT_RE.split(line.strip()):
                    sentence = sentence.strip(" -\t")
                    if not sentence:
                        continue
                    candidates.append(
                        {
                            "text": sentence,
                            "is_list_item": False,
                            "is_topic_sentence": not first_sentence_seen,
                        }
                    )
                    first_sentence_seen = True
        return candidates

    @staticmethod
    def _score(index: int, candidate: Dict, total: int) -> Dict:
        text = candidate["text"]
        word_count = len(text.split())
        reasons: List[str] = []
        score = 0.0

        if candidate["is_list_item"]:
            score += _SCORE_LIST_ITEM
            reasons.append("already an explicit list item")
        if candidate["is_topic_sentence"]:
            score += _SCORE_TOPIC_SENTENCE
            reasons.append("opens its paragraph")
        if _NUMBER_RE.search(text):
            score += _SCORE_HAS_NUMBER
            reasons.append("contains a number/stat")
        lowered = text.lower()
        if any(cue in lowered for cue in _CUE_WORDS):
            score += _SCORE_CUE_WORD
            reasons.append("contains a cue word")
        if index == 0:
            score += _SCORE_FIRST_OVERALL
            reasons.append("first candidate overall")

        if word_count < _MIN_WORDS:
            score -= _PENALTY_TOO_SHORT
            reasons.append(f"penalized: only {word_count} words")
        elif word_count > _MAX_WORDS:
            score -= _PENALTY_TOO_LONG
            reasons.append(f"penalized: {word_count} words is long for a single point")

        return {
            "text": text,
            "score": max(0.0, round(score, 3)),
            "reasons": reasons,
            "source": "list_item" if candidate["is_list_item"] else "sentence",
            "_order": index,
        }

    def extract_in_original_order(self, text: str, max_points: int = 5) -> List[Dict]:
        """Same ranking as extract(), but returned in the order the
        points appeared in the source text - what summarizer.py wants
        so a condensed summary still reads coherently front-to-back."""
        top = self.extract(text, max_points=max_points)
        return sorted(top, key=lambda c: c["_order"])


def get_point_extractor() -> PointExtractor:
    """Process-wide PointExtractor singleton (stateless, shared for consistency)."""
    global _instance
    if _instance is None:
        with _instance_lock:
            if _instance is None:
                _instance = PointExtractor()
    return _instance
