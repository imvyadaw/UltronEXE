"""
Always Listen
=============
The one module in EARS/ allowed to open a microphone, mirroring
EYES/live_camera.py's role for video. Backed by the `speech_recognition`
package (ambient mic capture + Google's free web recognizer as the
default engine) - both are optional; no mic hardware, no package
installed, or no network for the recognizer all degrade to
"unavailable" the same three-way-independent-failure way
live_camera.py treats "opencv missing" vs "device didn't open" as the
same externally-visible False.

"Wake word" here is a plain case-insensitive substring check against
the transcribed text (WAKE_WORDS), not a real always-on wake-word
model (Porcupine, etc.) - same "cheap heuristic, honestly labeled" call
this project keeps making. That means always_listen() actually
transcribes *every* utterance to check it, which is fine for a
push-to-talk-adjacent flow but is not a low-power always-on listener;
swapping in a real wake-word engine later only needs to change
`_contains_wake_word`, nothing about the calling convention.
"""

from typing import List, Optional

try:
    import speech_recognition as sr

    _SR_AVAILABLE = True
except Exception:
    _SR_AVAILABLE = False

WAKE_WORDS = ("ultron", "hey ultron")
DEFAULT_PHRASE_TIMEOUT_SECONDS = 6


class AlwaysListen:
    """Microphone capture + transcription + a wake-word substring
    check. Use get_always_listen()."""

    def __init__(self):
        self._recognizer = sr.Recognizer() if _SR_AVAILABLE else None

    def is_available(self) -> bool:
        if not _SR_AVAILABLE:
            return False
        try:
            with sr.Microphone():
                return True
        except Exception:
            return False

    def listen_once(self, timeout_seconds: int = DEFAULT_PHRASE_TIMEOUT_SECONDS) -> Optional[str]:
        """Captures one phrase from the default microphone and
        transcribes it. None on no mic, no speech, or a recognizer
        failure (including no network reaching the recognition
        service) - never an exception."""
        if not _SR_AVAILABLE:
            return None
        try:
            with sr.Microphone() as source:
                self._recognizer.adjust_for_ambient_noise(source, duration=0.5)
                audio = self._recognizer.listen(source, timeout=timeout_seconds, phrase_time_limit=timeout_seconds)
            return self._recognizer.recognize_google(audio)
        except Exception:
            return None

    def listen_for_wake_word(self, timeout_seconds: int = DEFAULT_PHRASE_TIMEOUT_SECONDS) -> bool:
        """Listens once and reports whether the transcript contained a
        wake word. False on no speech, no mic, or no match - the same
        collapse every other module here uses, since a caller in a
        loop only cares "keep waiting" vs "go"."""
        text = self.listen_once(timeout_seconds=timeout_seconds)
        return self._contains_wake_word(text)

    @staticmethod
    def _contains_wake_word(text: Optional[str]) -> bool:
        if not text:
            return False
        lowered = text.lower()
        return any(w in lowered for w in WAKE_WORDS)

    @staticmethod
    def wake_words() -> List[str]:
        return list(WAKE_WORDS)


_always_listen: Optional[AlwaysListen] = None


def get_always_listen() -> AlwaysListen:
    global _always_listen
    if _always_listen is None:
        _always_listen = AlwaysListen()
    return _always_listen
