"""
Mood analyzer for the movie assistant
========================================
Classifies free-text (English or Hinglish, matching the rest of this
codebase - see core/intent_router.py's Hinglish goal-intent patterns
for precedent) into one of a fixed set of moods movie_suggester.py
knows how to map to genres.

Default path is a pure keyword-overlap heuristic - instant, works
fully offline, no API cost, same design as ai/tool_selector.py's
ranking. analyze_with_brain() is available as an optional refinement
step for ambiguous/mixed text, following agents/analyst.py's
"_call_brain() only for interpretation, never for the deterministic
part" pattern - here the deterministic part is the keyword match, and
the brain is only asked to pick between close keyword-match
candidates, never to invent a mood with no textual support.
"""

import re
from typing import Dict, List, Optional

_WORD_RE = re.compile(r"[a-z0-9]+")

# mood -> keywords (English + common Hinglish/Hindi-in-Latin-script
# spellings). Kept short and high-precision rather than exhaustive -
# false positives are worse here than a missed match, since a missed
# match just falls back to "neutral" instead of misjudging the mood.
_MOOD_KEYWORDS: Dict[str, List[str]] = {
    "happy": [
        "happy",
        "great",
        "excited",
        "khush",
        "khushi",
        "mast",
        "badhiya",
        "awesome",
        "cheerful",
        "celebrating",
        "celebration",
        "party",
    ],
    "sad": [
        "sad",
        "down",
        "upset",
        "udaas",
        "dukhi",
        "depressed",
        "low",
        "heartbroken",
        "crying",
        "cry",
        "rona",
        "gum",
    ],
    "stressed": [
        "stressed",
        "stress",
        "tension",
        "anxious",
        "anxiety",
        "pareshan",
        "overwhelmed",
        "burnt out",
        "burnout",
        "exam",
        "deadline",
        "worried",
    ],
    "bored": [
        "bored",
        "bore",
        "boring",
        "kuch nahi karna",
        "nothing to do",
        "free hu",
        "free hoon",
        "timepass",
        "time pass",
    ],
    "romantic": [
        "romantic",
        "romance",
        "pyaar",
        "pyar",
        "love",
        "date night",
        "girlfriend",
        "boyfriend",
        "wife",
        "husband",
        "valentine",
    ],
    "adventurous": [
        "adventure",
        "adventurous",
        "thrill",
        "thrilling",
        "action",
        "josh",
        "excitement",
        "adrenaline",
    ],
    "nostalgic": [
        "nostalgic",
        "nostalgia",
        "old days",
        "childhood",
        "purani yaadein",
        "throwback",
        "yaadein",
        "miss those days",
    ],
    "angry": [
        "angry",
        "gussa",
        "irritated",
        "annoyed",
        "frustrated",
        "mad",
    ],
    "relaxed": [
        "relaxed",
        "chill",
        "chilling",
        "calm",
        "sukoon",
        "peaceful",
        "lazy",
        "lounging",
        "aaram",
    ],
    "scared": [
        "scared",
        "spooky",
        "horror",
        "dar",
        "darr",
        "creepy",
        "haunted",
    ],
}

_VALID_MOODS = set(_MOOD_KEYWORDS.keys())


def _words(text: str) -> List[str]:
    return _WORD_RE.findall(text.lower())


class MoodAnalyzer:
    """Text -> mood classification, keyword-based with optional LLM
    refinement for ambiguous input."""

    def analyze(self, text: str) -> Dict:
        """Returns {"mood": str, "confidence": float, "source": "keyword",
        "matched_keywords": [...], "candidates": {mood: score}}.
        `mood` defaults to "neutral" (no genre lean, movie_suggester.py
        just returns broadly popular picks) when nothing matches."""
        if not text or not text.strip():
            return {"mood": "neutral", "confidence": 0.0, "source": "empty", "matched_keywords": [], "candidates": {}}

        text_lower = text.lower()
        scores: Dict[str, int] = {}
        matched: Dict[str, List[str]] = {}
        for mood, keywords in _MOOD_KEYWORDS.items():
            hits = [kw for kw in keywords if kw in text_lower]
            if hits:
                scores[mood] = len(hits)
                matched[mood] = hits

        if not scores:
            return {"mood": "neutral", "confidence": 0.0, "source": "keyword", "matched_keywords": [], "candidates": {}}

        best_mood = max(scores, key=scores.get)
        top_score = scores[best_mood]
        total = sum(scores.values())
        confidence = round(top_score / total, 2) if total else 0.0

        return {
            "mood": best_mood,
            "confidence": confidence,
            "source": "keyword",
            "matched_keywords": matched[best_mood],
            "candidates": scores,
        }

    def analyze_with_brain(self, text: str) -> Dict:
        """Refines analyze()'s keyword result with an LLM call - only
        useful when analyze() found more than one close candidate
        (genuinely ambiguous text) or nothing at all (mood implied but
        no keyword matched). The brain is constrained to the same
        fixed mood list, never allowed to invent a new one, and its
        pick is discarded (keyword result kept) if it returns anything
        outside that list. Falls back to analyze()'s result untouched
        if the brain is unavailable."""
        keyword_result = self.analyze(text)
        candidates = keyword_result.get("candidates", {})
        is_ambiguous = len(candidates) >= 2 and keyword_result["confidence"] < 0.6
        is_empty = keyword_result["mood"] == "neutral" and not candidates
        if not (is_ambiguous or is_empty):
            return keyword_result

        brain_mood = self._call_brain_for_mood(text)
        if brain_mood and brain_mood in _VALID_MOODS:
            return {
                "mood": brain_mood,
                "confidence": 0.7,
                "source": "brain",
                "matched_keywords": keyword_result.get("matched_keywords", []),
                "candidates": candidates,
            }
        return keyword_result

    @staticmethod
    def _call_brain_for_mood(text: str) -> Optional[str]:
        """See agents/analyst.py's _call_brain() docstring - identical
        contract. Returns a single lowercase mood word or None."""
        try:
            from ai.cloud_models.groq_client import get_ultron_client as get_groq_client
        except Exception:
            return None
        try:
            client = get_groq_client()
            mood_list = ", ".join(sorted(_VALID_MOODS))
            system_prompt = (
                f"Classify the user's mood from this fixed list only: {mood_list}, "
                "or 'neutral' if none fit. The text may be in English or Hinglish "
                "(Hindi written in Latin script mixed with English). Reply with "
                "exactly one word from the list - nothing else."
            )
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": text},
            ]
            response = client.chat_with_tools(messages=messages, tools=[])
            content = response.get("content") or response.get("text") if isinstance(response, dict) else str(response)
            if not content:
                return None
            word = _words(content.strip())
            return word[0] if word else None
        except Exception:
            return None
