"""
Speaker recognition
=====================
No trained speaker-embedding model (resemblyzer, pyannote, etc.) is
bundled with this project, so this is a lightweight heuristic "voice
fingerprint" built from plain numpy: average pitch (autocorrelation-based
estimate), energy, and coarse spectral-band energy ratios from an
sr.AudioData clip. Good enough to tell two very different voices apart
(e.g. two family members) in a quiet room; it is NOT robust to noisy
audio, different microphones, or close-sounding voices - it should be
treated as a rough hint, never as an authentication mechanism.

Enrolled profiles (one averaged feature vector per name) persist under
storage/cache/speaker_profiles.json.
"""

import json
from pathlib import Path
from typing import Dict, List, Optional

try:
    import numpy as np

    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False

MATCH_THRESHOLD = 0.85  # cosine similarity - conservative, see module docstring


def _audio_to_samples(audio) -> "np.ndarray":
    raw = audio.get_raw_data(convert_rate=16000, convert_width=2)
    return np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0


def _estimate_pitch(samples: "np.ndarray", sample_rate: int = 16000) -> float:
    """Rough fundamental-frequency estimate via autocorrelation - fine
    for a coarse voiceprint feature, not accurate enough for music/tuning."""
    windowed = samples * np.hanning(len(samples))
    corr = np.correlate(windowed, windowed, mode="full")[len(windowed) - 1 :]
    min_lag, max_lag = sample_rate // 400, sample_rate // 70  # ~70-400 Hz human voice range
    if max_lag >= len(corr):
        return 0.0
    segment = corr[min_lag:max_lag]
    if len(segment) == 0 or segment.max() <= 0:
        return 0.0
    peak_lag = min_lag + int(np.argmax(segment))
    return sample_rate / peak_lag if peak_lag else 0.0


def _extract_features(audio) -> "np.ndarray":
    samples = _audio_to_samples(audio)
    if len(samples) < 512:
        samples = np.pad(samples, (0, 512 - len(samples)))

    energy = float(np.sqrt(np.mean(samples**2)))
    pitch = _estimate_pitch(samples)

    spectrum = np.abs(np.fft.rfft(samples * np.hanning(len(samples))))
    bands = np.array_split(spectrum, 6)  # coarse low->high frequency energy profile
    band_energy = [float(b.mean()) for b in bands]
    total = sum(band_energy) or 1.0
    band_ratios = [b / total for b in band_energy]

    return np.array([pitch / 300.0, energy] + band_ratios, dtype=np.float32)


def _cosine_similarity(a: "np.ndarray", b: "np.ndarray") -> float:
    denom = (np.linalg.norm(a) * np.linalg.norm(b)) or 1e-8
    return float(np.dot(a, b) / denom)


class SpeakerRecognizer:
    """Enroll a small number of known voices and identify which one a
    new audio clip most resembles - see module docstring for accuracy
    caveats."""

    def __init__(self):
        from config import CACHE_DIR

        self._path = Path(CACHE_DIR) / "speaker_profiles.json"
        self._profiles: Dict[str, List[float]] = {}
        self._load()

    def _load(self) -> None:
        if self._path.exists():
            try:
                with open(self._path, encoding="utf-8") as f:
                    self._profiles = json.load(f)
            except Exception:
                self._profiles = {}

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._path, "w", encoding="utf-8") as f:
            json.dump(self._profiles, f, indent=2)

    def enroll(self, name: str, audio) -> Dict:
        """Enroll (or update) a speaker's voiceprint from one audio clip.
        Call this a few times with fresh clips for a more stable profile -
        each call averages into the existing one rather than replacing it."""
        if not HAS_NUMPY:
            return {"error": "numpy not installed"}
        try:
            features = _extract_features(audio)
        except Exception as e:
            return {"error": str(e)}

        if name in self._profiles:
            existing = np.array(self._profiles[name], dtype=np.float32)
            features = (existing + features) / 2

        self._profiles[name] = features.tolist()
        self._save()
        return {"success": True, "enrolled": name}

    def identify(self, audio) -> Dict:
        """Return the best-matching enrolled name, or 'unknown' if
        nothing clears MATCH_THRESHOLD."""
        if not HAS_NUMPY:
            return {"error": "numpy not installed"}
        if not self._profiles:
            return {"speaker": "unknown", "confidence": 0.0, "note": "No speakers enrolled yet"}

        try:
            features = _extract_features(audio)
        except Exception as e:
            return {"error": str(e)}

        best_name, best_score = "unknown", 0.0
        for name, vector in self._profiles.items():
            score = _cosine_similarity(features, np.array(vector, dtype=np.float32))
            if score > best_score:
                best_name, best_score = name, score

        if best_score < MATCH_THRESHOLD:
            return {"speaker": "unknown", "confidence": round(best_score, 3)}
        return {"speaker": best_name, "confidence": round(best_score, 3)}

    def list_speakers(self) -> Dict:
        return {"count": len(self._profiles), "speakers": list(self._profiles.keys())}

    def forget_speaker(self, name: str) -> Dict:
        if name not in self._profiles:
            return {"error": f"No enrolled speaker named '{name}'"}
        del self._profiles[name]
        self._save()
        return {"success": True, "removed": name}

    def enroll_from_mic(self, name: str, duration: float = 4.0) -> Dict:
        """Record `duration` seconds from the default mic and enroll it -
        convenience for callers (e.g. a tool call) that don't already
        have an sr.AudioData clip on hand."""
        from voice.microphone.microphone import get_microphone

        audio = get_microphone().listen_once(timeout=duration + 2, phrase_time_limit=duration)
        if audio is None:
            return {"error": "Didn't hear anything - try again and speak right after calling this"}
        return self.enroll(name, audio)

    def identify_from_mic(self, duration: float = 4.0) -> Dict:
        """Record `duration` seconds from the default mic and identify
        the speaker."""
        from voice.microphone.microphone import get_microphone

        audio = get_microphone().listen_once(timeout=duration + 2, phrase_time_limit=duration)
        if audio is None:
            return {"error": "Didn't hear anything - try again and speak right after calling this"}
        return self.identify(audio)


_instance: Optional[SpeakerRecognizer] = None


def get_speaker_recognizer() -> SpeakerRecognizer:
    global _instance
    if _instance is None:
        _instance = SpeakerRecognizer()
    return _instance
