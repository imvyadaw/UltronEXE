"""
Ultron Voice
============
Wraps natural_speak.py with CORE.personality's current style, the same
relationship reports.py already has to personality.speak() for text -
this is that idea at the audio-parameter level. personality.current_style()
is read (dashboard.py already reads this same method for its own
snapshot) and mapped onto rate/volume; there's no pitch control in
pyttsx3's cross-platform API, so a "pitch" style hint, if present, is
accepted but not applied - documented here rather than silently
dropped.

Checks silent_mode.py before ever calling natural_speak.py - the
single enforcement point every other MOUTH/ module that wants to
"actually speak" should go through, rather than each one reimplementing
the same check.
"""

from typing import Dict, Optional

DEFAULT_RATE = 175
DEFAULT_VOLUME = 1.0

# current_style() keys this project's personality module might report,
# mapped to speak() parameters. Any style key not in this map is
# ignored rather than guessed at.
STYLE_RATE_ADJUST = {
    "energetic": 25,  # words/min faster
    "calm": -20,
    "formal": -10,
    "casual": 10,
}


class UltronVoice:
    """Personality-styled speech output. Use get_ultron_voice()."""

    def speak(self, text: str) -> Dict:
        """Speaks `text` styled by the current personality, unless
        silent_mode is on. Always returns
        {"text": str, "spoken": bool, "rate": int, "volume": float} -
        `spoken` is False either because silent_mode is on or because
        the underlying engine couldn't play it; callers that only need
        the text (e.g. to log or display) can read `text` regardless."""
        rate, volume = self._styled_params()

        if self._is_silent():
            return {"text": text, "spoken": False, "rate": rate, "volume": volume}

        try:
            from mouth.natural_speak import get_natural_speak

            spoken = get_natural_speak().speak(text, rate=rate, volume=volume)
        except Exception:
            spoken = False

        return {"text": text, "spoken": spoken, "rate": rate, "volume": volume}

    @staticmethod
    def _is_silent() -> bool:
        try:
            from mouth.silent_mode import get_silent_mode

            return get_silent_mode().is_silent()
        except Exception:
            return False

    @staticmethod
    def _styled_params() -> tuple:
        rate, volume = DEFAULT_RATE, DEFAULT_VOLUME
        try:
            from core.personality import get_personality

            style = get_personality().current_style() or {}
            mood = style.get("mood") or style.get("tone")
            rate += STYLE_RATE_ADJUST.get(mood, 0)
            if "volume" in style:
                volume = float(style["volume"])
        except Exception:
            from core.error_trace import log_swallowed as _lsw

            _lsw("mouth.ultron_voice._styled_params")
        return rate, volume


_ultron_voice: Optional[UltronVoice] = None


def get_ultron_voice() -> UltronVoice:
    global _ultron_voice
    if _ultron_voice is None:
        _ultron_voice = UltronVoice()
    return _ultron_voice
