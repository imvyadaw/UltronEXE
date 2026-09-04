"""
Mood Predict (PREDICT)
==========================
A lightweight, lexicon-based tone signal from short text - meant for
adjusting how Ultron phrases a reply (warmer, terser, more upbeat),
nothing more. This is NOT a diagnostic or clinical tool: it has no
concept of mental health conditions, makes no claims about what
someone is "actually" feeling, and should never be surfaced to a user
as an assessment of them. Treat its output the same way you'd treat
"the last message used a lot of exclamation points" - a shallow
surface signal, not an inference about a person's inner state.

Scoring is a simple positive/negative keyword count (plus a few
punctuation/emoji cues) normalized to a single "valence" score from
-1.0 (very negative wording) to 1.0 (very positive wording), with an
"energy" score from 0.0 to 1.0 based on length, punctuation intensity
and capitalization. No external NLP library, no training data beyond
the small hand-written lexicon below - swap _LEXICON for something
larger later without changing this module's interface.
"""

import re
from typing import Dict, List, Optional

_POSITIVE_WORDS = {
    "great",
    "good",
    "awesome",
    "love",
    "happy",
    "excited",
    "thanks",
    "thank",
    "nice",
    "wonderful",
    "glad",
    "excellent",
    "fantastic",
    "amazing",
    "perfect",
    "yay",
}
_NEGATIVE_WORDS = {
    "bad",
    "terrible",
    "hate",
    "angry",
    "annoyed",
    "frustrated",
    "sad",
    "awful",
    "worst",
    "ugh",
    "tired",
    "exhausted",
    "stressed",
    "upset",
    "annoying",
    "sucks",
}
_WORD_RE = re.compile(r"[a-zA-Z']+")


class MoodPredict:
    """Heuristic text tone scoring. Use get_mood_predict()."""

    def predict(self, text: str) -> Dict:
        """Scores `text` for surface tone only. Returns {"valence":
        float, "energy": float, "label": str}, where "label" is one
        of "positive"/"neutral"/"negative" derived purely from
        `valence`'s sign and magnitude - a coarse bucket for a caller
        that just wants a quick branch, not a substitute for the raw
        scores. Empty or whitespace-only text returns neutral/zero
        scores rather than raising."""
        if not text or not text.strip():
            return {"valence": 0.0, "energy": 0.0, "label": "neutral"}

        words = [w.lower() for w in _WORD_RE.findall(text)]
        positive_hits = sum(1 for w in words if w in _POSITIVE_WORDS)
        negative_hits = sum(1 for w in words if w in _NEGATIVE_WORDS)
        total_hits = positive_hits + negative_hits
        valence = 0.0 if total_hits == 0 else (positive_hits - negative_hits) / total_hits

        exclamations = text.count("!")
        caps_words = sum(1 for w in re.findall(r"[A-Za-z']+", text) if w.isupper() and len(w) > 1)
        energy = min(1.0, (exclamations * 0.15) + (caps_words * 0.1) + min(len(words), 20) / 40)

        if valence > 0.2:
            label = "positive"
        elif valence < -0.2:
            label = "negative"
        else:
            label = "neutral"

        return {"valence": round(valence, 3), "energy": round(energy, 3), "label": label}

    def predict_trend(self, texts: List[str]) -> Dict:
        """Averages predict() across `texts` (oldest first) and
        reports whether valence is trending up, down, or flat across
        them via a simple first-half-vs-second-half comparison.
        Returns {"average_valence": float, "average_energy": float,
        "trend": str}. Fewer than 2 texts always reports trend
        "flat", since a trend needs at least two points to compare."""
        if not texts:
            return {"average_valence": 0.0, "average_energy": 0.0, "trend": "flat"}
        scored = [self.predict(t) for t in texts]
        avg_valence = sum(s["valence"] for s in scored) / len(scored)
        avg_energy = sum(s["energy"] for s in scored) / len(scored)
        if len(scored) < 2:
            return {"average_valence": round(avg_valence, 3), "average_energy": round(avg_energy, 3), "trend": "flat"}

        midpoint = len(scored) // 2
        first_half_avg = sum(s["valence"] for s in scored[:midpoint]) / midpoint
        second_half_avg = sum(s["valence"] for s in scored[midpoint:]) / (len(scored) - midpoint)
        delta = second_half_avg - first_half_avg
        trend = "up" if delta > 0.1 else "down" if delta < -0.1 else "flat"

        return {"average_valence": round(avg_valence, 3), "average_energy": round(avg_energy, 3), "trend": trend}


_mood_predict: Optional[MoodPredict] = None


def get_mood_predict() -> MoodPredict:
    global _mood_predict
    if _mood_predict is None:
        _mood_predict = MoodPredict()
    return _mood_predict
