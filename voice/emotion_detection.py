"""
Emotion detection
==================
No trained speech-emotion-recognition model is bundled with this
project, so voice emotion here is threshold-based on plain acoustic
features - pitch level/variance, energy (loudness), and zero-crossing
rate (a rough proxy for speaking rate/harshness) - bucketed into a small
set of coarse categories. This is a best-effort heuristic, not a
clinical or reliably accurate signal; treat it as a mood hint at most,
never as a basis for a consequential decision about the user.

analyze_text_sentiment() is a separate, much simpler keyword-based
fallback for when only transcribed text (not raw audio) is available.
"""

from typing import Dict, Optional

try:
    import numpy as np

    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False

POSITIVE_WORDS = {
    "great",
    "good",
    "awesome",
    "love",
    "happy",
    "thanks",
    "thank",
    "excellent",
    "nice",
    "perfect",
    "amazing",
    "yay",
    "glad",
    "cool",
    "wonderful",
}
NEGATIVE_WORDS = {
    "bad",
    "hate",
    "angry",
    "annoyed",
    "frustrated",
    "terrible",
    "awful",
    "sad",
    "upset",
    "worst",
    "ugh",
    "sucks",
    "stupid",
    "broken",
    "wrong",
}


def _audio_to_samples(audio) -> "np.ndarray":
    raw = audio.get_raw_data(convert_rate=16000, convert_width=2)
    return np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0


def _zero_crossing_rate(samples: "np.ndarray") -> float:
    signs = np.sign(samples)
    signs[signs == 0] = 1
    crossings = np.count_nonzero(np.diff(signs))
    return float(crossings / len(samples)) if len(samples) else 0.0


def _estimate_pitch_series(samples: "np.ndarray", sample_rate: int = 16000, frame_ms: int = 40):
    frame_len = int(sample_rate * frame_ms / 1000)
    pitches = []
    for start in range(0, len(samples) - frame_len, frame_len):
        frame = samples[start : start + frame_len] * np.hanning(frame_len)
        corr = np.correlate(frame, frame, mode="full")[frame_len - 1 :]
        min_lag, max_lag = sample_rate // 400, sample_rate // 70
        if max_lag >= len(corr):
            continue
        segment = corr[min_lag:max_lag]
        if len(segment) == 0 or segment.max() <= 0:
            continue
        peak_lag = min_lag + int(np.argmax(segment))
        if peak_lag:
            pitches.append(sample_rate / peak_lag)
    return pitches


class EmotionDetector:
    """Coarse, heuristic voice-emotion bucketing from raw acoustic
    features - see module docstring for accuracy caveats."""

    def analyze_audio(self, audio) -> Dict:
        if not HAS_NUMPY:
            return {"error": "numpy not installed"}
        try:
            samples = _audio_to_samples(audio)
            if len(samples) < 512:
                return {"error": "Clip too short to analyze"}

            energy = float(np.sqrt(np.mean(samples**2)))
            zcr = _zero_crossing_rate(samples)
            pitches = _estimate_pitch_series(samples)
            pitch_mean = float(np.mean(pitches)) if pitches else 0.0
            pitch_std = float(np.std(pitches)) if len(pitches) > 1 else 0.0

            emotion, confidence = self._classify(energy, zcr, pitch_mean, pitch_std)

            return {
                "emotion": emotion,
                "confidence": confidence,
                "features": {
                    "energy": round(energy, 4),
                    "zero_crossing_rate": round(zcr, 4),
                    "pitch_mean_hz": round(pitch_mean, 1),
                    "pitch_variance_hz": round(pitch_std, 1),
                },
                "note": "Heuristic acoustic estimate, not a trained emotion-recognition model.",
            }
        except Exception as e:
            return {"error": str(e)}

    @staticmethod
    def _classify(energy: float, zcr: float, pitch_mean: float, pitch_std: float):
        # Loud + high pitch variance + fast (high ZCR) -> excited/happy or angry;
        # tell those two apart with pitch level (anger tends to run lower/harsher,
        # happiness higher). Quiet + flat pitch -> sad/calm. Otherwise neutral.
        loud = energy > 0.06
        expressive = pitch_std > 18
        fast = zcr > 0.09
        high_pitch = pitch_mean > 190

        if loud and expressive and fast:
            return ("happy_excited", 0.6) if high_pitch else ("angry_stressed", 0.55)
        if not loud and pitch_std < 10:
            return "sad_calm", 0.5
        if loud and not expressive:
            return "angry_stressed", 0.45
        return "neutral", 0.5

    def analyze_text_sentiment(self, text: str) -> Dict:
        """Simple keyword-based sentiment hint for when only transcribed
        text is available (no raw audio) - much weaker signal than the
        acoustic path, but zero dependencies and instant."""
        words = set(w.strip(".,!?").lower() for w in text.split())
        pos = len(words & POSITIVE_WORDS)
        neg = len(words & NEGATIVE_WORDS)
        if pos == neg:
            sentiment = "neutral"
        elif pos > neg:
            sentiment = "positive"
        else:
            sentiment = "negative"
        return {"sentiment": sentiment, "positive_hits": pos, "negative_hits": neg}

    def analyze_from_mic(self, duration: float = 4.0) -> Dict:
        """Record `duration` seconds from the default mic and run the
        acoustic emotion analysis on it - convenience for callers (e.g.
        a tool call) that don't already have an sr.AudioData clip."""
        from voice.microphone.microphone import get_microphone

        audio = get_microphone().listen_once(timeout=duration + 2, phrase_time_limit=duration)
        if audio is None:
            return {"error": "Didn't hear anything - try again and speak right after calling this"}
        return self.analyze_audio(audio)


_instance: Optional[EmotionDetector] = None


def get_emotion_detector() -> EmotionDetector:
    global _instance
    if _instance is None:
        _instance = EmotionDetector()
    return _instance
