"""
Voice activity detector (VAD)
===============================
Frame-by-frame "is someone speaking right now" classification for the
20-80ms PCM frames voice/microphone/stream.py's MicrophoneStream already
yields for wake word detection - this module scores the same frames for
speech presence instead of a keyword, which is what full_duplex_engine.py
and interrupt_handler.py both need.

Two backends, same interface, picked automatically:
  - webrtcvad, if installed: Google's production VAD (WebRTC), fast and
    much more reliable than an energy threshold, especially in noisy
    rooms. Not a hard dependency - not in requirements.txt - so it's
    optional.
  - Fallback: a plain energy + zero-crossing-rate heuristic, the same
    kind of "no bundled model, just numpy" approach voice/emotion_detection.py
    and voice/speaker_recognition.py already take, with a short rolling
    noise-floor estimate so it adapts to room volume instead of using a
    fixed threshold.

Both backends only ever answer "speech in *this* frame, yes/no" -
turning that into "the user started/stopped talking" (debouncing across
several frames) is is_speaking()'s job, kept separate so a caller who
only wants the raw per-frame signal (e.g. a live VU meter) can call
score_frame() directly.
"""

from collections import deque
from typing import Deque, Optional

try:
    import numpy as np

    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False

try:
    import webrtcvad

    HAS_WEBRTCVAD = True
except ImportError:
    HAS_WEBRTCVAD = False

from core.logger import get_logger

logger = get_logger("ultron.interaction.vad")

SAMPLE_RATE = 16000
# webrtcvad only accepts 10/20/30ms frames at this rate.
WEBRTC_FRAME_MS = 30
WEBRTC_AGGRESSIVENESS = 2  # 0 (lenient) - 3 (aggressive), see webrtcvad docs

# Debounce: consecutive speech/silence frames needed before flipping state,
# so a single noisy frame doesn't toggle is_speaking() back and forth.
SPEECH_ON_FRAMES = 2
SPEECH_OFF_FRAMES = 8  # a bit longer, so a mid-sentence pause doesn't count as "done"


def _pcm16_bytes_to_samples(frame: bytes) -> "np.ndarray":
    return np.frombuffer(frame, dtype=np.int16).astype(np.float32) / 32768.0


class VoiceActivityDetector:
    """Stateful per-stream VAD - one instance per conversation/stream,
    not shared, since it tracks a rolling noise floor and on/off debounce
    state that only makes sense for one continuous audio source."""

    def __init__(self, aggressiveness: int = WEBRTC_AGGRESSIVENESS):
        self._webrtc = None
        if HAS_WEBRTCVAD:
            try:
                self._webrtc = webrtcvad.Vad(aggressiveness)
            except Exception as e:
                logger.warning(f"webrtcvad init failed, falling back to energy VAD: {e}")

        self._noise_floor = 0.01
        self._speaking = False
        self._streak = 0
        self._recent: Deque[bool] = deque(maxlen=SPEECH_OFF_FRAMES)

    @property
    def backend(self) -> str:
        return "webrtcvad" if self._webrtc is not None else "energy" if HAS_NUMPY else "unavailable"

    def score_frame(self, frame: bytes) -> bool:
        """Classify one raw 16-bit PCM mono frame as speech/not-speech.
        Stateless w.r.t. the on/off debounce - use is_speaking() for that."""
        if self._webrtc is not None:
            try:
                return self._webrtc.is_speech(frame, SAMPLE_RATE)
            except Exception as e:
                logger.debug(f"webrtcvad frame scoring failed, using energy fallback: {e}")

        if not HAS_NUMPY:
            return False

        samples = _pcm16_bytes_to_samples(frame)
        if len(samples) == 0:
            return False

        energy = float(np.sqrt(np.mean(samples**2)))
        # Slowly adapt the noise floor toward quiet frames only, so a
        # sustained loud sound doesn't drag the threshold up and make
        # the detector deaf to normal speech.
        if energy < self._noise_floor * 1.5:
            self._noise_floor = 0.95 * self._noise_floor + 0.05 * energy

        zcr = float(np.count_nonzero(np.diff(np.sign(samples))) / len(samples))
        return energy > max(self._noise_floor * 4, 0.015) and 0.02 < zcr < 0.5

    def is_speaking(self, frame: bytes) -> bool:
        """Feed one frame, get back the debounced "is the user currently
        talking" state - call this in a loop over a live stream."""
        speech = self.score_frame(frame)
        self._recent.append(speech)

        if speech:
            self._streak = self._streak + 1 if self._streak >= 0 else 1
        else:
            self._streak = self._streak - 1 if self._streak <= 0 else -1

        if not self._speaking and self._streak >= SPEECH_ON_FRAMES:
            self._speaking = True
        elif self._speaking and sum(self._recent) == 0 and len(self._recent) == self._recent.maxlen:
            self._speaking = False

        return self._speaking

    def reset(self) -> None:
        self._speaking = False
        self._streak = 0
        self._recent.clear()


_default_vad: Optional[VoiceActivityDetector] = None


def get_vad() -> VoiceActivityDetector:
    """Shared VAD instance for callers that just want a default detector
    rather than managing their own (e.g. a quick one-off check) -
    full_duplex_engine.py and interrupt_handler.py create their own
    instances instead, since each tracks independent stream state."""
    global _default_vad
    if _default_vad is None:
        _default_vad = VoiceActivityDetector()
    return _default_vad
