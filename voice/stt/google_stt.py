"""
Google Web Speech STT backend
==============================
The "cloud" leg of the STT hybrid - extracted out of stt_engine.py (which
is now purely an orchestrator, see that file) so each engine lives in its
own file per the Phase 9 layout. Free, no API key, but needs internet and
sends audio to Google's servers - see voice/stt/vosk_stt.py or
voice/stt/whisper_stt.py for fully offline alternatives.
"""

import os
from typing import Optional

try:
    import speech_recognition as sr

    HAS_SPEECH_RECOGNITION = True
except ImportError:
    HAS_SPEECH_RECOGNITION = False

from config import STT_LANGUAGE
from core.logger import get_logger

logger = get_logger("google_stt")


class GoogleSTT:
    """Thin wrapper around SpeechRecognition's recognize_google()."""

    def __init__(self, language: str = STT_LANGUAGE):
        if not HAS_SPEECH_RECOGNITION:
            raise RuntimeError("SpeechRecognition not installed - run: pip install SpeechRecognition")
        self.language = language
        self.recognizer = sr.Recognizer()
        # SpeechRecognition's recognize_google() opens a plain urllib
        # request under the hood using this attribute as its timeout, and
        # it defaults to None (no timeout) if never set - meaning a
        # stalled/dead connection here blocks forever on a call that runs
        # on literally every voice turn. 10s is generous for a single
        # short-audio recognition request.
        self.recognizer.operation_timeout = 10

    def transcribe(self, audio, language: Optional[str] = None) -> Optional[str]:
        """Transcribe an sr.AudioData object. Returns None on unclear
        speech or when the request couldn't reach Google (caller should
        fall back to an offline engine in that case). `language`
        overrides self.language for this one call (used by
        transcribe_audio_data()'s Hindi retry below)."""
        if audio is None:
            return None
        try:
            return self.recognizer.recognize_google(audio, language=language or self.language)
        except sr.UnknownValueError:
            return None
        except sr.RequestError as e:
            logger.info("Google STT unreachable: %s", e)
            return None


def is_available() -> bool:
    return HAS_SPEECH_RECOGNITION


_instance: Optional[GoogleSTT] = None


def get_google_stt() -> GoogleSTT:
    global _instance
    if _instance is None:
        _instance = GoogleSTT()
    return _instance


# Second language tried when the primary (config.STT_LANGUAGE, "en-IN" by
# default) comes back with nothing - covers actual spoken Hindi, which
# en-IN's model doesn't recognize well, without the user having to
# manually switch modes. Only costs a second network round-trip on turns
# where the first attempt genuinely found nothing to transcribe, so
# normal English/Hinglish turns (which en-IN already handles fine) pay
# no extra cost. Set STT_LANGUAGE_SECONDARY="" in .env to disable this.
STT_LANGUAGE_SECONDARY = os.getenv("STT_LANGUAGE_SECONDARY", "hi-IN")


def transcribe_audio_data(audio) -> Optional[str]:
    """Module-level convenience matching whisper_stt.py/vosk_stt.py's
    function-style API, for callers that don't need a persistent instance.
    Tries config.STT_LANGUAGE first; if that comes back empty, retries
    once in STT_LANGUAGE_SECONDARY (Hindi by default) - see that
    constant's comment above."""
    stt = get_google_stt()
    text = stt.transcribe(audio)
    if text is not None:
        return text
    if STT_LANGUAGE_SECONDARY and STT_LANGUAGE_SECONDARY != STT_LANGUAGE:
        return stt.transcribe(audio, language=STT_LANGUAGE_SECONDARY)
    return None
