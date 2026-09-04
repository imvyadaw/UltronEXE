"""
Style emulation
=================
Two stages:

  1. analyze_style() - a pure-stdlib, offline pass over a writing
     sample that extracts a small set of measurable style features
     (avg sentence length, vocabulary richness, punctuation habits,
     common sentence openers, contraction usage, average word
     length). No model call needed for this half - these are plain
     counts, same "cheap deterministic pass before touching the
     model" instinct as modules/movie_assistant/mood_analyzer.py's
     keyword pass.
  2. generate_in_style() - feeds that profile (plus a short excerpt of
     the original sample as a concrete anchor) into
     ai.ai_router.complete() as conditioning, asking it to write new
     text matching the measured style rather than describing the
     style in vague adjectives.

Kept deliberately lightweight (no real NLP library dependency) - good
enough to meaningfully steer generation, not a stylometric research
tool.
"""

import re
import statistics
from typing import Dict, List

_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")
_WORD_RE = re.compile(r"[A-Za-z']+")
_CONTRACTION_RE = re.compile(r"\b\w+'(t|re|ve|ll|d|s|m)\b", re.IGNORECASE)


def analyze_style(sample_text: str) -> Dict:
    """Returns a style profile dict:
        {
          "avg_sentence_length_words": float,
          "avg_word_length_chars": float,
          "vocabulary_richness": float,   # unique words / total words
          "contraction_rate": float,       # contractions per 100 words
          "exclamation_rate": float,       # "!" per sentence
          "common_openers": [str, ...],    # up to 5 most common first words
          "sample_excerpt": str,           # first ~200 chars, for anchoring
        }
    Returns zeros/empty for an empty or whitespace-only sample rather
    than raising - callers can check word_count before trusting the
    other fields."""
    text = (sample_text or "").strip()
    if not text:
        return {
            "word_count": 0,
            "avg_sentence_length_words": 0.0,
            "avg_word_length_chars": 0.0,
            "vocabulary_richness": 0.0,
            "contraction_rate": 0.0,
            "exclamation_rate": 0.0,
            "common_openers": [],
            "sample_excerpt": "",
        }

    sentences = [s.strip() for s in _SENTENCE_SPLIT_RE.split(text) if s.strip()]
    words = _WORD_RE.findall(text)
    word_count = len(words)

    sentence_lengths = [len(_WORD_RE.findall(s)) for s in sentences] or [word_count]
    avg_sentence_len = round(statistics.mean(sentence_lengths), 2) if sentence_lengths else 0.0
    avg_word_len = round(statistics.mean(len(w) for w in words), 2) if words else 0.0
    richness = round(len(set(w.lower() for w in words)) / word_count, 3) if word_count else 0.0
    contractions = len(_CONTRACTION_RE.findall(text))
    contraction_rate = round((contractions / word_count) * 100, 2) if word_count else 0.0
    exclamations = text.count("!")
    exclamation_rate = round(exclamations / len(sentences), 2) if sentences else 0.0

    openers: List[str] = []
    seen_counts: Dict[str, int] = {}
    for s in sentences:
        w = _WORD_RE.findall(s)
        if w:
            first = w[0].lower()
            seen_counts[first] = seen_counts.get(first, 0) + 1
    common_openers = [w for w, _ in sorted(seen_counts.items(), key=lambda kv: kv[1], reverse=True)[:5]]

    return {
        "word_count": word_count,
        "avg_sentence_length_words": avg_sentence_len,
        "avg_word_length_chars": avg_word_len,
        "vocabulary_richness": richness,
        "contraction_rate": contraction_rate,
        "exclamation_rate": exclamation_rate,
        "common_openers": common_openers,
        "sample_excerpt": text[:200],
    }


def generate_in_style(prompt: str, sample_text: str, max_tokens: int = 500) -> Dict:
    """Generate new text for `prompt`, styled after `sample_text`.
    Returns {"success": bool, "text": str, "style_profile": {...}}."""
    profile = analyze_style(sample_text)
    if profile["word_count"] == 0:
        from ai.ai_router import get_router

        try:
            text = get_router().complete(prompt, temperature=0.6, max_tokens=max_tokens)
            return {
                "success": True,
                "text": text,
                "style_profile": profile,
                "note": "no sample provided - default style used",
            }
        except Exception as e:
            return {"success": False, "text": "", "style_profile": profile, "error": str(e)}

    style_desc = (
        f"average sentence length ~{profile['avg_sentence_length_words']} words, "
        f"average word length ~{profile['avg_word_length_chars']} characters, "
        f"{'frequent' if profile['contraction_rate'] > 3 else 'rare'} use of contractions, "
        f"{'frequent' if profile['exclamation_rate'] > 0.3 else 'sparing'} use of exclamation marks, "
        f"vocabulary richness score {profile['vocabulary_richness']}"
    )
    style_prompt = (
        "Write the following, matching this writer's style as closely as "
        f"possible ({style_desc}). Here is a short excerpt of their actual "
        f"writing to match the voice of:\n\n\"{profile['sample_excerpt']}\"\n\n"
        f"Now write this in that same voice:\n{prompt}"
    )
    from ai.ai_router import get_router

    try:
        text = get_router().complete(style_prompt, temperature=0.6, max_tokens=max_tokens)
        return {"success": True, "text": text, "style_profile": profile}
    except Exception as e:
        return {"success": False, "text": "", "style_profile": profile, "error": str(e)}
