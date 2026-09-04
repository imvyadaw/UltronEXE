"""
Natural Speak
=============
The one module in MOUTH/ allowed to touch a TTS engine, mirroring
always_listen.py's role for the microphone. Backed by `pyttsx3`
(offline, no network round-trip, works the same on a dev box with no
internet as it will on-device) - if it's not installed, or no voice
driver is available on this system (a headless CI box, a stripped
container), speak() returns False and logs the text instead, same
"log what would have happened" fallback screen_popup.py already uses
for a headless display.

Deliberately synchronous and blocking, same as screen_popup.show()'s
auto-close wait - this module doesn't manage a speech queue; a caller
wanting several lines spoken in order just calls speak() several
times.
"""

import time
from typing import Dict, List, Optional

try:
    import pyttsx3

    _PYTTSX3_AVAILABLE = True
except Exception:
    _PYTTSX3_AVAILABLE = False

DEFAULT_RATE = 175  # words per minute, pyttsx3's own default ballpark
DEFAULT_VOLUME = 1.0  # 0.0-1.0


class NaturalSpeak:
    """Base TTS engine wrapper. Use get_natural_speak()."""

    def __init__(self):
        self._engine = None
        if _PYTTSX3_AVAILABLE:
            try:
                self._engine = pyttsx3.init()
            except Exception:
                self._engine = None
        self._log: List[Dict] = []

    def is_available(self) -> bool:
        return self._engine is not None

    def speak(self, text: str, rate: int = DEFAULT_RATE, volume: float = DEFAULT_VOLUME) -> bool:
        """Speaks `text` at the given rate (words/min) and volume
        (0.0-1.0). Returns True only if the engine actually spoke;
        False (with the attempt still logged) on no engine or any
        runtime failure."""
        entry = {"text": text, "rate": rate, "volume": volume, "logged_at": time.time()}
        self._log.append(entry)

        if not self.is_available() or not text:
            return False
        try:
            self._engine.setProperty("rate", rate)
            self._engine.setProperty("volume", max(0.0, min(1.0, volume)))
            self._engine.say(text)
            self._engine.runAndWait()
            return True
        except Exception:
            return False

    def available_voices(self) -> List[str]:
        """Returns installed voice ids/names, or [] if unavailable -
        ultron_voice.py can use this to pick a voice if the platform
        offers more than one, without this module deciding which."""
        if not self.is_available():
            return []
        try:
            return [v.id for v in self._engine.getProperty("voices")]
        except Exception:
            return []

    def set_voice(self, voice_id: str) -> bool:
        if not self.is_available():
            return False
        try:
            self._engine.setProperty("voice", voice_id)
            return True
        except Exception:
            return False

    def recent(self, limit: int = 20) -> List[Dict]:
        return self._log[-limit:]


_natural_speak: Optional[NaturalSpeak] = None


def get_natural_speak() -> NaturalSpeak:
    global _natural_speak
    if _natural_speak is None:
        _natural_speak = NaturalSpeak()
    return _natural_speak
