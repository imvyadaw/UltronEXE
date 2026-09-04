"""
Empathy engine
===============
Complements voice/emotion_detection.py (which owns the actual emotion
DETECTION, both acoustic and text-keyword) rather than re-detecting
anything:

  - emotion_simulator.py: turns a detected emotion (from
    voice/emotion_detection.py's analyze_audio()/analyze_text_sentiment(),
    or a plain emotion label) into a small valence/arousal
    representation plus a recommended response POSTURE (e.g. "de-
    escalate", "celebrate-with", "give-space") - a bridge between raw
    detection output and "how should the reply actually behave".
  - supportive_response.py: turns that posture into an actual
    empathetic reply opener, in the existing bilingual "bhai" voice,
    explicitly NOT a clinical/therapeutic response generator - see
    its own docstring for the line it deliberately stays on the safe
    side of.
"""

from empathy_engine.emotion_simulator import simulate_emotional_state
from empathy_engine.supportive_response import generate_supportive_reply

__all__ = ["simulate_emotional_state", "generate_supportive_reply"]
