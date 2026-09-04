"""
Emotion simulator
===================
NOT a simulated inner life for Ultron (see core/personality.py's own
docstring for that same caution about its trait profile) - this is a
mapping layer: detected-user-emotion -> a small valence/arousal
number pair + a recommended response POSTURE, so downstream response
generation has one clean signal to act on instead of re-interpreting
a raw emotion label every time.

valence: -1 (very negative) .. +1 (very positive)
arousal:  0 (calm/low-energy) .. 1 (high-energy/agitated)
These two numbers are the standard circumplex-model axes used in
affective computing for exactly this kind of coarse mapping - not a
precise measurement, just a consistent small vocabulary two modules
can agree on.

posture is the actual behavioral recommendation:
  "celebrate_with"   - high valence, any arousal -> match the energy
  "de_escalate"       - negative valence, high arousal (angry/scared) ->
                         calm, short sentences, no jokes
  "comfort"           - negative valence, low arousal (sad) -> gentle,
                         validating, unhurried
  "give_space"        - negative valence, very high arousal + low
                         confidence signal -> acknowledge briefly,
                         don't push further questions
  "neutral"           - anything else -> normal delivery
"""

from typing import Dict, Optional

# emotion label (from voice/emotion_detection.py's acoustic categories
# or analyze_text_sentiment's positive/negative/neutral, plus the
# broader labels modules/movie_assistant/mood_analyzer.py already
# uses) -> (valence, arousal)
_EMOTION_MAP = {
    "positive": (0.6, 0.5),
    "happy": (0.8, 0.6),
    "excited": (0.8, 0.9),
    "calm": (0.4, 0.1),
    "neutral": (0.0, 0.3),
    "negative": (-0.5, 0.5),
    "sad": (-0.7, 0.2),
    "angry": (-0.7, 0.9),
    "frustrated": (-0.6, 0.7),
    "stressed": (-0.5, 0.8),
    "anxious": (-0.5, 0.8),
    "scared": (-0.6, 0.85),
    "bored": (-0.2, 0.1),
}


def _posture_for(valence: float, arousal: float, confidence: float) -> str:
    if valence >= 0.3:
        return "celebrate_with"
    if valence <= -0.3:
        if arousal >= 0.75 and confidence < 0.5:
            return "give_space"
        if arousal >= 0.6:
            return "de_escalate"
        return "comfort"
    return "neutral"


def simulate_emotional_state(
    emotion: Optional[str] = None, confidence: float = 0.6, text: Optional[str] = None
) -> Dict:
    """Pass an already-detected `emotion` label directly, OR `text` to
    have voice.emotion_detection's analyze_text_sentiment() detect a
    coarse positive/negative/neutral first. Returns:
        {"emotion": str, "valence": float, "arousal": float,
         "posture": str, "confidence": float}
    Unrecognized emotion labels map to neutral rather than raising -
    an unmapped label is far more likely than a wrong response here."""
    if not emotion and text:
        try:
            from voice.emotion_detection import get_emotion_detector

            result = get_emotion_detector().analyze_text_sentiment(text)
            emotion = result.get("sentiment", "neutral")
            hits = result.get("positive_hits", 0) + result.get("negative_hits", 0)
            confidence = min(0.9, 0.4 + hits * 0.15)
        except Exception:
            emotion = "neutral"

    emotion = (emotion or "neutral").lower()
    valence, arousal = _EMOTION_MAP.get(emotion, (0.0, 0.3))
    posture = _posture_for(valence, arousal, confidence)

    return {
        "emotion": emotion,
        "valence": valence,
        "arousal": arousal,
        "posture": posture,
        "confidence": round(confidence, 2),
    }
