"""
Emotion Read
============
Facial expression is the one signal in EYES/ where there's no honest
cheap heuristic to fall back on the way aHash stands in for face
embeddings - a hand-rolled "mouth-corner-position means happy" rule is
exactly the kind of fake-precise heuristic this project has
consistently avoided (see face_scanner.py's and threat_sense.py's
docstrings). So this module is an honestly-marked stub, same category
Phase 17 already put vision/face_recognition.py in: it defines the
interface (read_emotion(frame) -> Optional[Dict]) and best-effort
delegates to an installed third-party model (the `fer` package) if
one's available, otherwise returns None every time, clearly, rather
than guessing.

memory/emotional_memory.py already owns the user's mood as reported
through conversation - nothing here writes there. If a caller wants to
feed a camera-read emotion into that system later, that's a deliberate
follow-up wiring decision, not something this module should do
silently.
"""

from typing import Dict, Optional

try:
    from fer import FER

    _FER_AVAILABLE = True
except Exception:
    _FER_AVAILABLE = False


class EmotionReader:
    """Best-effort facial expression reading. Use get_emotion_reader()."""

    def __init__(self):
        self._detector = None
        if _FER_AVAILABLE:
            try:
                self._detector = FER()
            except Exception:
                self._detector = None

    def is_available(self) -> bool:
        return self._detector is not None

    def read_emotion(self, frame) -> Optional[Dict]:
        """Returns {"label": str, "confidence": float} for the
        strongest-scoring face in frame, or None - no model installed,
        no face found, or any failure all collapse to the same None.
        Never fabricates an emotion when the model isn't there."""
        if not self.is_available() or frame is None:
            return None
        try:
            results = self._detector.detect_emotions(frame)
            if not results:
                return None
            emotions = results[0].get("emotions", {})
            if not emotions:
                return None
            label, confidence = max(emotions.items(), key=lambda kv: kv[1])
            return {"label": label, "confidence": round(float(confidence), 3)}
        except Exception:
            return None


_emotion_reader: Optional[EmotionReader] = None


def get_emotion_reader() -> EmotionReader:
    global _emotion_reader
    if _emotion_reader is None:
        _emotion_reader = EmotionReader()
    return _emotion_reader
