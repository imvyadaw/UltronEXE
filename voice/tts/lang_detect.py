"""
Per-sentence language detection for TTS voice switching
=========================================================
Answers exactly one question for voice/tts/tts_engine.py: does this
sentence need a Hindi-capable voice/backend-language instead of the
English-India default?

Deliberately just a Devanagari-Unicode-range (U+0900-U+097F) check, not
`langdetect` - the actual bug this fixes is ULTRON's Devanagari-script
replies (from Hindi Wikipedia results, or a Hindi voice-typed question)
going through TTS_VOICE (an English-locale edge-tts voice) and
GTTS_LANG (fixed to "en"), which either mispronounce or silently fail
to render Devanagari at all - so text was shown on screen but nothing
was ever spoken. A Unicode range check catches that with zero
dependencies and zero false negatives on this specific failure mode.

Romanized Hinglish ("aap kaise ho", "kal milte hai") is intentionally
NOT flagged as Hindi here - TTS_VOICE already reads Roman-script text
fine regardless of which language the words are; that was never the
part that broke. Switching romanized text to a Hindi voice/lang would
just make the English words in a Hinglish sentence sound wrong.
"""

import re

_DEVANAGARI_RE = re.compile(r"[\u0900-\u097F]")


def is_hindi_script(text: str) -> bool:
    """True if `text` contains at least one Devanagari character."""
    return bool(text) and bool(_DEVANAGARI_RE.search(text))
