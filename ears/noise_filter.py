"""
Noise Filter
============
Cleans a raw audio chunk (a 1-D numpy float array) before anything
else in EARS/ touches it. Two tiers, same "best available result, not
a crash" contract night_eye.py uses for video:

  1. If `noisereduce` is installed, use its spectral-gating noise
     reduction against a noise-profile sample (the first
     NOISE_PROFILE_SECONDS of the clip, on the assumption that's
     mostly room tone before speech starts - a real VAD-based split
     would be better but isn't bundled here).
  2. If not, fall back to a plain high-pass Butterworth-style filter
     via scipy (removes low-frequency hum, not real noise reduction).
  3. If neither scipy nor numpy is available, return the audio
     unchanged - filtering isn't possible, but a caller that just
     wants "the best audio available" shouldn't have to special-case
     that.

None of these three tiers touch loudness/normalization - that's a
separate concern this module doesn't take on.
"""

from typing import Optional

try:
    _NUMPY_AVAILABLE = True
except Exception:
    _NUMPY_AVAILABLE = False

try:
    import noisereduce as nr

    _NOISEREDUCE_AVAILABLE = True
except Exception:
    _NOISEREDUCE_AVAILABLE = False

try:
    from scipy.signal import butter, lfilter

    _SCIPY_AVAILABLE = True
except Exception:
    _SCIPY_AVAILABLE = False

NOISE_PROFILE_SECONDS = 0.5
HIGH_PASS_CUTOFF_HZ = 100


class NoiseFilter:
    """Best-effort audio cleanup. Use get_noise_filter()."""

    def is_available(self) -> bool:
        return _NUMPY_AVAILABLE

    def clean(self, audio, sample_rate: int = 16000):
        """Returns a cleaned copy of `audio` (numpy float array), or
        `audio` unchanged if no cleaning method is available."""
        if not _NUMPY_AVAILABLE or audio is None:
            return audio
        try:
            if _NOISEREDUCE_AVAILABLE:
                profile_len = int(sample_rate * NOISE_PROFILE_SECONDS)
                noise_sample = audio[:profile_len] if len(audio) > profile_len else audio
                return nr.reduce_noise(y=audio, sr=sample_rate, y_noise=noise_sample)
            if _SCIPY_AVAILABLE:
                return self._high_pass(audio, sample_rate)
            return audio
        except Exception:
            return audio

    @staticmethod
    def _high_pass(audio, sample_rate: int):
        nyquist = 0.5 * sample_rate
        normal_cutoff = HIGH_PASS_CUTOFF_HZ / nyquist
        b, a = butter(2, normal_cutoff, btype="high", analog=False)
        return lfilter(b, a, audio)


_noise_filter: Optional[NoiseFilter] = None


def get_noise_filter() -> NoiseFilter:
    global _noise_filter
    if _noise_filter is None:
        _noise_filter = NoiseFilter()
    return _noise_filter
