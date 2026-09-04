"""
Real-time translator
=======================
Hinglish is already the working language of most of this codebase's
own comments/prompts (see core/intent_router.py's Hinglish intent
patterns, modules/movie_assistant/mood_analyzer.py's keyword lists),
so this module treats "Hinglish" as a first-class target, not just
"Hindi" - i.e. romanized Hindi mixed with English, matching how the
user actually types, rather than Devanagari.

Two tiers, cheapest first:
  1. A tiny built-in dictionary + transliteration table for extremely
     common short phrases/words (greetings, yes/no, thanks, numbers) -
     instant, fully offline, zero API cost - same "cheap deterministic
     path before touching the model" instinct as
     modules/movie_assistant/mood_analyzer.py's keyword pass before
     analyze_with_brain().
  2. ai.ai_router.complete() for anything not covered by tier 1 - one
     single-shot prompt, no tools, no shared conversation history
     mutation (same guarantee ai/reasoning.py and ai/planning.py rely
     on), so calling this mid-conversation never pollutes the live
     chat_with_tools() history.

detect_language() is a lightweight heuristic (script + a short list of
very common Hindi/Hinglish tokens), not a real language-ID model - good
enough to decide "does this need translating at all", not a research-
grade classifier.
"""

import re
from typing import Dict, Optional

from core.logger import get_logger

logger = get_logger("realtime_translator")

_DEVANAGARI_RE = re.compile(r"[\u0900-\u097F]")
_WORD_RE = re.compile(r"[a-zA-Z]+")

# Small closed set of extremely common Hinglish/Hindi-in-Latin-script
# tokens -> English. Deliberately short and high-precision (same
# philosophy as mood_analyzer.py's keyword lists) - anything not in
# here just falls through to the model tier instead of guessing.
_HINGLISH_TO_ENGLISH = {
    "namaste": "hello",
    "namaskar": "hello",
    "kaise ho": "how are you",
    "kaisa hai": "how is it",
    "kya haal hai": "what's up",
    "shukriya": "thank you",
    "dhanyavaad": "thank you",
    "dhanyavad": "thank you",
    "haan": "yes",
    "haanji": "yes",
    "nahi": "no",
    "nahin": "no",
    "theek hai": "okay",
    "thik hai": "okay",
    "accha": "good",
    "achha": "good",
    "bahut accha": "very good",
    "bura": "bad",
    "kya": "what",
    "kaun": "who",
    "kab": "when",
    "kahan": "where",
    "kyun": "why",
    "kaise": "how",
    "kitna": "how much",
    "ghar": "home",
    "paani": "water",
    "khana": "food",
    "subah": "morning",
    "shaam": "evening",
    "raat": "night",
    "alvida": "goodbye",
    "phir milenge": "see you again",
}
_ENGLISH_TO_HINGLISH = {v: k for k, v in _HINGLISH_TO_ENGLISH.items()}

# Common Hindi/Hinglish function words used only for detect_language()'s
# heuristic - not a translation table. Also folds in every single-word
# key from the dictionary above, so a bare dictionary hit like
# "namaste" or "shukriya" is correctly flagged hinglish/hindi too,
# not just multi-word phrases already covered by _HINGLISH_TO_ENGLISH.
_HINGLISH_MARKERS = {
    "hai",
    "hain",
    "ho",
    "kya",
    "nahi",
    "nahin",
    "aur",
    "kar",
    "karo",
    "kaise",
    "mera",
    "meri",
    "tumhara",
    "aap",
    "bhai",
    "yaar",
    "matlab",
    "abhi",
    "thoda",
    "bahut",
    "acha",
    "accha",
} | {k for k in _HINGLISH_TO_ENGLISH if " " not in k}


def detect_language(text: str) -> str:
    """Returns "hindi" (Devanagari script present), "hinglish"
    (Latin script but recognizably Hindi-flavored), or "english"."""
    if not text or not text.strip():
        return "english"
    if _DEVANAGARI_RE.search(text):
        return "hindi"
    words = {w.lower() for w in _WORD_RE.findall(text)}
    hits = words & _HINGLISH_MARKERS
    if len(hits) >= 1 and len(words) > 0 and (len(hits) / max(len(words), 1)) >= 0.15:
        return "hinglish"
    return "english"


def romanize_hindi(devanagari_text: str) -> str:
    """Best-effort Devanagari -> romanized-Hindi (Hinglish spelling),
    via the model (no offline transliteration table bundled here -
    doing this correctly needs real phoneme rules, not a lookup
    table). Returns the input unchanged if it contains no Devanagari
    at all, so calling this speculatively on already-Latin text is
    always a safe no-op."""
    if not _DEVANAGARI_RE.search(devanagari_text or ""):
        return devanagari_text
    from ai.ai_router import get_router

    prompt = (
        "Transliterate the following Hindi (Devanagari) text into "
        "romanized Hindi/Hinglish spelling, the way a Hindi speaker "
        'would casually type it in Latin letters (e.g. "kaise ho", not '
        "formal IAST transliteration). Reply with ONLY the transliterated "
        f"text, nothing else.\n\nText: {devanagari_text}"
    )
    try:
        return get_router().complete(prompt, temperature=0.1, max_tokens=300).strip()
    except Exception as e:
        logger.info("romanize_hindi model call failed: %s", e)
        return devanagari_text


def _dictionary_lookup(text: str, target_lang: str) -> Optional[str]:
    key = text.strip().lower()
    if target_lang in ("english", "en"):
        return _HINGLISH_TO_ENGLISH.get(key)
    if target_lang in ("hindi", "hinglish", "hi"):
        return _ENGLISH_TO_HINGLISH.get(key)
    return None


def translate(text: str, target_lang: str = "english", source_lang: Optional[str] = None) -> Dict:
    """Translate `text` into `target_lang` ("english", "hindi",
    "hinglish", or any language name the model understands, e.g.
    "spanish", "tamil"). Returns:
        {"success": bool, "translated": str, "source_lang": str,
         "target_lang": str, "via": "dictionary"|"model"}
    Empty/whitespace input returns success with an empty translation
    rather than making a wasted model call."""
    if not text or not text.strip():
        return {
            "success": True,
            "translated": "",
            "source_lang": source_lang or "unknown",
            "target_lang": target_lang,
            "via": "dictionary",
        }

    detected = source_lang or detect_language(text)

    quick = _dictionary_lookup(text, target_lang)
    if quick is not None:
        return {
            "success": True,
            "translated": quick,
            "source_lang": detected,
            "target_lang": target_lang,
            "via": "dictionary",
        }

    from ai.ai_router import get_router

    style_hint = (
        " Use natural Hinglish (romanized Hindi mixed with English, casual "
        "everyday phrasing), not formal Hindi and not Devanagari script."
        if target_lang.lower() in ("hindi", "hinglish", "hi")
        else ""
    )
    prompt = (
        f"Translate the following text into {target_lang}.{style_hint} "
        "Reply with ONLY the translation, no explanation, no quotes.\n\n"
        f"Text: {text}"
    )
    try:
        translated = get_router().complete(prompt, temperature=0.2, max_tokens=500).strip()
        return {
            "success": True,
            "translated": translated,
            "source_lang": detected,
            "target_lang": target_lang,
            "via": "model",
        }
    except Exception as e:
        logger.info("translate() model call failed: %s", e)
        return {
            "success": False,
            "translated": "",
            "source_lang": detected,
            "target_lang": target_lang,
            "via": "model",
            "error": str(e),
        }
