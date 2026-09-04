"""
Emotion analyzer
===================
Fuses voice/emotion_detection.py's two independent signals - acoustic
emotion from raw audio (EmotionDetector.analyze_audio) and keyword-based
text sentiment (EmotionDetector.analyze_text_sentiment) - into one
combined read, since a full_duplex_engine.py turn naturally has both an
audio clip and its transcript available at the same time and neither
signal alone is very reliable (see emotion_detection.py's own accuracy
caveats - this module inherits the same "best-effort hint, not a
clinical signal" caveat and does not strengthen the underlying
heuristics, only combines them).

Used by custom_tts_engine.py to pick reply prosody, and by
context_aware_dashboard.py / holographic_orb.py (ADAPTIVE_UI) to show a
mood indicator - never to make a decision about the user, per the same
caution voice/emotion_detection.py's own docstring calls for.
"""

from typing import Dict, Optional

from voice.emotion_detection import get_emotion_detector
from core.logger import get_logger

logger = get_logger("ultron.interaction.emotion")

# Acoustic buckets (from emotion_detection.py) mapped onto a small,
# TTS-prosody-relevant set custom_tts_engine.py consumes directly.
_ACOUSTIC_TO_MOOD = {
    "happy_excited": "upbeat",
    "angry_stressed": "tense",
    "sad_calm": "subdued",
    "neutral": "neutral",
}


class EmotionAnalyzer:
    """Stateless combiner over EmotionDetector - safe as a shared
    singleton (get_emotion_analyzer() below), unlike SpeakerDiarizer
    which needs per-session state."""

    def __init__(self):
        self._detector = get_emotion_detector()

    def analyze(self, audio=None, text: Optional[str] = None) -> Dict:
        """Combine acoustic (if `audio` given) and text (if `text`
        given) signals. Either can be omitted - e.g. full_duplex_engine.py
        may only have the transcript by the time this is called if the
        raw clip wasn't retained."""
        acoustic = self._detector.analyze_audio(audio) if audio is not None else None
        textual = self._detector.analyze_text_sentiment(text) if text else None

        mood = "neutral"
        confidence = 0.3
        source = "default"

        if acoustic and "emotion" in acoustic:
            mood = _ACOUSTIC_TO_MOOD.get(acoustic["emotion"], "neutral")
            confidence = acoustic.get("confidence", 0.5)
            source = "acoustic"

        if textual:
            # Text sentiment can reinforce or override a low-confidence
            # acoustic read (e.g. quiet, sarcastic "great, thanks" - flat
            # acoustic signal but clearly negative words), but a strong
            # acoustic read isn't overridden by a weak text signal.
            if textual["sentiment"] == "negative" and mood in ("neutral", "upbeat") and confidence < 0.55:
                mood, source = "tense", "text+acoustic" if acoustic else "text"
            elif textual["sentiment"] == "positive" and mood == "neutral" and confidence < 0.55:
                mood, source = "upbeat", "text+acoustic" if acoustic else "text"

        return {
            "mood": mood,
            "confidence": round(confidence, 2),
            "source": source,
            "acoustic": acoustic,
            "text_sentiment": textual,
        }


_analyzer: Optional[EmotionAnalyzer] = None


def get_emotion_analyzer() -> EmotionAnalyzer:
    global _analyzer
    if _analyzer is None:
        _analyzer = EmotionAnalyzer()
    return _analyzer
