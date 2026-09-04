"""
Hindi English
=============
short_term.py's REFERENCE_WORDS already carries a Hindi set
(yeh/woh/yahan/wahan) alongside the English one, so this project has
already assumed Hindi-English code-switching without ever detecting it
explicitly. This module closes that gap at the text level, over an
already-transcribed utterance (always_listen.py's job, not this
module's) - not over raw audio, since language ID from transcribed
text is both cheaper and more reliable than doing it acoustically.

Two tiers, same shape as noise_filter.py:

  1. `langdetect` if installed, run per-sentence so a mixed utterance
     ("mujhe ek meeting schedule karni hai for tomorrow") is reported
     as "mixed" instead of forcing one label onto the whole thing.
  2. If not installed, a plain Devanagari-Unicode-range check plus a
     small transliterated-Hindi word list (reusing
     short_term.REFERENCE_WORDS' Hindi entries as a seed, extended a
     little) - cruder, but works with zero extra dependencies for the
     common case of romanized Hindi mixed into English.

detect() never raises and never returns an empty label - "unknown" is
the honest fallback when neither tier can decide.
"""

import re
from typing import Dict, List, Optional

try:
    from langdetect import detect_langs

    _LANGDETECT_AVAILABLE = True
except Exception:
    _LANGDETECT_AVAILABLE = False

DEVANAGARI_RANGE = re.compile(r"[\u0900-\u097F]")

# Seeded from short_term.py's REFERENCE_WORDS Hindi entries, extended
# with a few more common romanized-Hindi function words - a small,
# honest heuristic list, not a lexicon.
ROMAN_HINDI_WORDS = {
    "yeh",
    "woh",
    "yahan",
    "wahan",
    "kya",
    "hai",
    "nahi",
    "haan",
    "mujhe",
    "aap",
    "tum",
    "kaise",
    "kyun",
    "kab",
    "kahan",
}


class HindiEnglish:
    """Text-level Hindi/English/mixed language identification. Use get_hindi_english()."""

    def is_available(self) -> bool:
        return True  # the fallback tier always works

    def detect(self, text: str) -> Dict:
        """Returns {"label": "hindi"|"english"|"mixed"|"unknown",
        "confidence": float}. confidence is only meaningful when
        langdetect ran; the fallback tier reports a fixed 0.5 since
        it's a word-list heuristic, not a scored model."""
        if not text or not text.strip():
            return {"label": "unknown", "confidence": 0.0}

        if DEVANAGARI_RANGE.search(text):
            has_ascii_words = bool(re.search(r"[A-Za-z]{2,}", text))
            return {"label": "mixed" if has_ascii_words else "hindi", "confidence": 0.9}

        if _LANGDETECT_AVAILABLE:
            try:
                langs = detect_langs(text)
                top = langs[0]
                if top.lang == "hi":
                    return {"label": "hindi", "confidence": round(top.prob, 3)}
                if top.lang == "en":
                    # langdetect on romanized Hindi often still says "en" -
                    # cross-check against the roman-Hindi word list before
                    # trusting that.
                    if self._roman_hindi_fraction(text) >= 0.2:
                        return {"label": "mixed", "confidence": round(top.prob, 3)}
                    return {"label": "english", "confidence": round(top.prob, 3)}
                return {"label": "unknown", "confidence": round(top.prob, 3)}
            except Exception:
                from core.error_trace import log_swallowed as _lsw

                _lsw("ears.hindi_english.detect")

        fraction = self._roman_hindi_fraction(text)
        if fraction >= 0.4:
            return {"label": "hindi", "confidence": 0.5}
        if fraction > 0:
            return {"label": "mixed", "confidence": 0.5}
        return {"label": "english", "confidence": 0.5}

    @staticmethod
    def _roman_hindi_fraction(text: str) -> float:
        words: List[str] = re.findall(r"[A-Za-z]+", text.lower())
        if not words:
            return 0.0
        hits = sum(1 for w in words if w in ROMAN_HINDI_WORDS)
        return hits / len(words)


_hindi_english: Optional[HindiEnglish] = None


def get_hindi_english() -> HindiEnglish:
    global _hindi_english
    if _hindi_english is None:
        _hindi_english = HindiEnglish()
    return _hindi_english
