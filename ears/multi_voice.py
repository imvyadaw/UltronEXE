"""
Multi Voice
===========
Answers "is this the same speaker as before in this session?", not
"who is this" - naming a voice permanently would mean growing a
persistent voice-embedding table, which is MEMORY/'s kind of decision
to make (the same way face_scanner.py stayed out of the naming
business and left that to MEMORY/face_memory.py), not something to
smuggle into EARS/ unasked.

The fingerprint is a coarse pitch + spectral-centroid summary (mean +
std of the fundamental frequency estimate, mean spectral centroid) -
cheap, numpy-only, and explicitly not a trained speaker-embedding
model (nothing here is a resemblyzer/pyannote replacement). Matching
is nearest-fingerprint-within-tolerance among speakers seen so far
*this session*; the registry resets every time the process restarts,
same lifetime MEMORY/short_term.py already gives session-scoped state.
"""

import math
from typing import Dict, List, Optional

try:
    import numpy as np

    _NUMPY_AVAILABLE = True
except Exception:
    _NUMPY_AVAILABLE = False

PITCH_TOLERANCE_HZ = 25
CENTROID_TOLERANCE_HZ = 400


class MultiVoice:
    """Session-scoped speaker fingerprinting (not identity). Use get_multi_voice()."""

    def __init__(self):
        self._speakers: List[Dict] = []  # [{"id": int, "pitch_mean": float, "centroid_mean": float}]

    def is_available(self) -> bool:
        return _NUMPY_AVAILABLE

    def identify_speaker(self, audio, sample_rate: int = 16000) -> Optional[int]:
        """Returns a session-local integer speaker id: an existing one
        if the fingerprint is close to a speaker already seen, a new
        one otherwise. None if fingerprinting isn't possible (no numpy
        or empty audio)."""
        fingerprint = self._fingerprint(audio, sample_rate)
        if fingerprint is None:
            return None

        for speaker in self._speakers:
            if (
                abs(speaker["pitch_mean"] - fingerprint["pitch_mean"]) <= PITCH_TOLERANCE_HZ
                and abs(speaker["centroid_mean"] - fingerprint["centroid_mean"]) <= CENTROID_TOLERANCE_HZ
            ):
                return speaker["id"]

        new_id = len(self._speakers)
        self._speakers.append({"id": new_id, **fingerprint})
        return new_id

    def known_speaker_count(self) -> int:
        return len(self._speakers)

    def reset(self) -> None:
        """Clears the session's speaker registry - e.g. on a new
        conversation or if the room's occupants have plausibly
        changed. There's no persistence to clear beyond this object's
        own state."""
        self._speakers = []

    @staticmethod
    def _fingerprint(audio, sample_rate: int) -> Optional[Dict]:
        if not _NUMPY_AVAILABLE or audio is None or len(audio) < sample_rate * 0.2:
            return None
        try:
            audio = np.asarray(audio, dtype=float)
            windowed = audio * np.hanning(len(audio))
            spectrum = np.abs(np.fft.rfft(windowed))
            freqs = np.fft.rfftfreq(len(windowed), d=1.0 / sample_rate)

            if spectrum.sum() <= 0:
                return None

            # crude pitch estimate: frequency bin with peak magnitude
            # in a plausible human-voice band
            voice_band = (freqs >= 75) & (freqs <= 400)
            if not voice_band.any() or spectrum[voice_band].max() <= 0:
                pitch_mean = 0.0
            else:
                pitch_mean = float(freqs[voice_band][np.argmax(spectrum[voice_band])])

            centroid_mean = float((freqs * spectrum).sum() / spectrum.sum())

            if pitch_mean == 0.0 and not math.isfinite(centroid_mean):
                return None
            return {"pitch_mean": pitch_mean, "centroid_mean": centroid_mean}
        except Exception:
            return None


_multi_voice: Optional[MultiVoice] = None


def get_multi_voice() -> MultiVoice:
    global _multi_voice
    if _multi_voice is None:
        _multi_voice = MultiVoice()
    return _multi_voice
