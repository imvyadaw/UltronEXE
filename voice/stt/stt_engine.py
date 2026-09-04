"""
Speech-to-text (orchestrator)
================================
Routes to whichever concrete STT engine config.STT_MODE (+ STT_LANGUAGE)
call for. Each engine now lives in its own module (Phase 9 layout):

    voice/stt/google_stt.py   - cloud, Google Web Speech API (free, no key)
    voice/stt/whisper_stt.py  - offline, faster-whisper
    voice/stt/vosk_stt.py     - offline, Vosk - smaller/faster than Whisper,
                                 and has a dedicated Hindi model

Policy (config.STT_MODE):
    auto (default) -> STT_LANGUAGE is Hindi and a Vosk Hindi model is
                       present -> Vosk Hindi (best Hindi accuracy, fully
                       offline)
                       otherwise online -> Google; Google fails/unreachable
                       or offline -> local Whisper
    cloud -> Google only, no fallback (errors out with no internet)
    local -> local Whisper only, fully offline, never touches the network
    vosk  -> local Vosk only, fully offline, never touches the network

voice/wakeword/wakeword.py's legacy STT-based detector calls into this
same engine for its continuous listen loop, so wake word detection
inherits this same offline fallback automatically.
"""

from typing import Optional

try:
    HAS_SPEECH_RECOGNITION = True
except ImportError:
    HAS_SPEECH_RECOGNITION = False

from voice.microphone.microphone import get_microphone
from voice.stt import whisper_stt, vosk_stt, google_stt
from config import STT_LANGUAGE, STT_MODE, COMMAND_LISTEN_TIMEOUT, COMMAND_PHRASE_TIME_LIMIT
from core.internet_monitor import is_online
from core.logger import get_logger

logger = get_logger("stt_engine")


def _is_hindi(language: str) -> bool:
    return language.split("-")[0].lower() == "hi"


class SpeechToText:
    """Hybrid speech-to-text - picks the right concrete engine per
    config.STT_MODE/STT_LANGUAGE for each call. See module docstring."""

    def __init__(self, language: str = STT_LANGUAGE):
        if not HAS_SPEECH_RECOGNITION:
            raise RuntimeError("SpeechRecognition not installed - run: pip install SpeechRecognition PyAudio")
        self.language = language

    def transcribe_audio(self, audio) -> Optional[str]:
        """Transcribe an sr.AudioData object (from Microphone.listen_once)
        to text, per STT_MODE's policy. Returns None if speech was
        unintelligible or nothing was available to transcribe with."""
        if audio is None:
            return None

        if STT_MODE == "vosk":
            return vosk_stt.transcribe_audio_data(audio, self.language)

        if STT_MODE == "local":
            return whisper_stt.transcribe_audio_data(audio)

        if STT_MODE == "cloud":
            return google_stt.transcribe_audio_data(audio)

        # auto (default)
        if _is_hindi(self.language) and vosk_stt.is_available(self.language):
            text = vosk_stt.transcribe_audio_data(audio, self.language)
            if text is not None:
                return text
            # Vosk heard nothing intelligible - still worth trying cloud/
            # Whisper below rather than giving up outright.

        if is_online():
            text = google_stt.transcribe_audio_data(audio)
            if text is not None:
                return text
            # is_online() said yes but the actual request failed (flaky
            # connection, Google hiccup) - try offline engines before
            # giving up.

        if _is_hindi(self.language) and vosk_stt.is_available(self.language):
            return vosk_stt.transcribe_audio_data(audio, self.language)

        return whisper_stt.transcribe_audio_data(audio)

    def transcribe_from_mic(
        self,
        timeout: Optional[float] = COMMAND_LISTEN_TIMEOUT,
        phrase_time_limit: Optional[float] = COMMAND_PHRASE_TIME_LIMIT,
    ) -> Optional[str]:
        """Listen once on the default microphone and transcribe it."""
        mic = get_microphone()
        audio = mic.listen_once(timeout=timeout, phrase_time_limit=phrase_time_limit)
        return self.transcribe_audio(audio)


_stt_instance: Optional[SpeechToText] = None


def get_stt() -> SpeechToText:
    global _stt_instance
    if _stt_instance is None:
        _stt_instance = SpeechToText()
    return _stt_instance
