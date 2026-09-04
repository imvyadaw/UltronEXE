"""
Microphone capture
==================
Captures raw audio from the system's default microphone using the
SpeechRecognition library (which wraps PyAudio under the hood).
Hands AudioData objects to voice/stt/ and voice/wakeword/.

Tuned for responsiveness: ambient-noise calibration is quick (see
config.MIC_CALIBRATION_SECONDS) and the recognizer's pause_threshold is
lowered (config.MIC_PAUSE_THRESHOLD) so Ultron stops listening and starts
responding shortly after you stop talking, instead of waiting out the
library's default ~0.8s of silence.
"""

from typing import Optional

try:
    import speech_recognition as sr

    HAS_SPEECH_RECOGNITION = True
except ImportError:
    HAS_SPEECH_RECOGNITION = False

from config import MIC_CALIBRATION_SECONDS, MIC_PAUSE_THRESHOLD


class Microphone:
    """Thin wrapper around sr.Microphone + sr.Recognizer with ambient-noise
    calibration done once at startup instead of on every listen() call."""

    def __init__(self, device_index: Optional[int] = None):
        if not HAS_SPEECH_RECOGNITION:
            raise RuntimeError(
                "SpeechRecognition/PyAudio not installed - run: " "pip install SpeechRecognition PyAudio"
            )
        self.recognizer = sr.Recognizer()
        self.recognizer.pause_threshold = MIC_PAUSE_THRESHOLD
        self.recognizer.non_speaking_duration = min(0.3, MIC_PAUSE_THRESHOLD)
        self.device_index = device_index
        self._mic = sr.Microphone(device_index=device_index)
        self._calibrated = False

    def calibrate(self, duration: float = MIC_CALIBRATION_SECONDS):
        """Sample ambient noise once so silence detection is accurate.
        Call this at startup before the first listen()."""
        with self._mic as source:
            self.recognizer.adjust_for_ambient_noise(source, duration=duration)
        self._calibrated = True

    def listen_once(
        self, timeout: Optional[float] = None, phrase_time_limit: Optional[float] = None, denoise: Optional[bool] = None
    ):
        """Block until a phrase is captured (or timeout). Returns an
        sr.AudioData object, or None if nothing was heard before timeout.

        `denoise`: run voice/noise_cancellation.py's spectral-subtraction
        pass on the captured clip before returning it. Defaults to
        voice.noise_cancellation.DENOISE_ENABLED when not given explicitly;
        pass False to skip it for a single call. Never raises - falls
        back to the raw, un-denoised clip on any failure.
        """
        if not self._calibrated:
            self.calibrate()

        with self._mic as source:
            try:
                audio = self.recognizer.listen(source, timeout=timeout, phrase_time_limit=phrase_time_limit)
            except sr.WaitTimeoutError:
                return None

        try:
            from voice.noise_cancellation import DENOISE_ENABLED, denoise_audio_data

            should_denoise = DENOISE_ENABLED if denoise is None else denoise
            if should_denoise:
                audio = denoise_audio_data(audio)
        except Exception:
            from core.error_trace import log_swallowed as _lsw

            _lsw("voice.microphone.microphone.listen_once")
        return audio

    @staticmethod
    def list_microphones():
        """List available microphone device names/indices, for picking a
        non-default device via Microphone(device_index=N)."""
        if not HAS_SPEECH_RECOGNITION:
            return []
        return list(enumerate(sr.Microphone.list_microphone_names()))


_mic_instance: Optional[Microphone] = None


def get_microphone() -> Microphone:
    global _mic_instance
    if _mic_instance is None:
        _mic_instance = Microphone()
    return _mic_instance
