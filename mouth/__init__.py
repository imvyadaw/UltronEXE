"""
MOUTH (Phase 18.4)
====================
The audio-out counterpart to DISPLAY/: EARS/ produces data (transcripts,
speaker ids, language labels); nothing in EARS/ speaks. MOUTH/ is the
output side.

    natural_speak.py - the one module that actually calls a TTS
                        engine (pyttsx3, offline). Everything else in
                        this package either wraps it with a style or
                        decides whether to call it at all - same
                        "one module owns the device" separation
                        EYES/live_camera.py and EARS/always_listen.py
                        both draw.
    ultron_voice.py   - applies CORE.personality's current style
                        (rate/volume/pitch, to the extent the
                        installed TTS engine's voice supports pitch at
                        all) to natural_speak.py, the same way
                        reports.py already wraps its summary text
                        through personality.speak() before returning
                        it - this is that same idea one layer down, at
                        the audio parameters instead of the words.
    whisper_talk.py   - a quiet-mode variant (lower volume, slower
                        rate) for contexts where a full-volume reply
                        is wrong - late night, a meeting, a
                        caller-specified "quietly" request. Wraps
                        ultron_voice.py rather than natural_speak.py
                        directly, so whisper mode still carries
                        personality's style on top of its own volume/
                        rate override.
    auto_reply.py     - a small fixed-vocabulary quick-reply table for
                        latency-sensitive one-liners ("what time is
                        it", a greeting), same "cheap heuristic, not
                        an LLM round-trip" call
                        COMMAND/control_panel.py's execute() already
                        makes for admin commands. Unmatched input
                        returns None so the caller falls through to
                        the real reasoning pipeline, never a guess.
    silent_mode.py    - a single in-memory toggle. When on,
                        ultron_voice.py and whisper_talk.py check it
                        before calling natural_speak.py and silently
                        skip playback (still returning the text) -
                        text output keeps working, only audio is
                        muted.

Same contract as EARS/ and DISPLAY/: optional dependencies checked
once at import time, every public method degrades rather than raises,
cross-package imports stay lazy.

Purely additive.
"""

from mouth.natural_speak import get_natural_speak
from mouth.ultron_voice import get_ultron_voice
from mouth.whisper_talk import get_whisper_talk
from mouth.auto_reply import get_auto_reply
from mouth.silent_mode import get_silent_mode

__all__ = [
    "get_natural_speak",
    "get_ultron_voice",
    "get_whisper_talk",
    "get_auto_reply",
    "get_silent_mode",
]
