"""
Advanced personality
======================
Two tone-detection/tone-generation additions that plug into the
existing personality stack instead of starting a new one:

  - sarcasm_detector.py: a text heuristic (same "keyword/pattern pass,
    zero dependencies, instant" philosophy as
    voice/emotion_detection.py's analyze_text_sentiment) for whether a
    message is likely sarcastic - useful so a literal-reading response
    doesn't take a sarcastic compliment/complaint at face value.
  - humor_engine.py: extends core/personality.py's existing (until now
    unused) "humor" trait into an actual joke/pun bank, gated by that
    trait's current value so a light aside only fires as often as the
    slowly-drifting personality profile says it should - not a fixed
    rate independent of the rest of the personality system.
"""

from advanced_personality.sarcasm_detector import detect_sarcasm
from advanced_personality.humor_engine import maybe_joke, get_joke

__all__ = ["detect_sarcasm", "maybe_joke", "get_joke"]
