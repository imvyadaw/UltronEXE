"""
Emotion Hear
============
The audio counterpart to EYES/emotion_read.py, and an honest stub for
the same reason: there's no cheap heuristic for vocal emotion this
project can back up the way aHash backs up face_scanner.py's
embedding_id or the pitch/centroid summary backs up multi_voice.py's
speaker fingerprint - pitch and energy alone are not emotion, and a
hand-rolled "high pitch + fast = excited" rule would be exactly the
kind of fake-precise guess this project has avoided everywhere else.

Defines the interface (read_emotion(audio) -> Optional[Dict]),
best-effort delegates to an installed third-party model if one's
available, otherwise returns None every time. Nothing here writes to
memory/emotional_memory.py - same boundary EYES/emotion_read.py drew,
for the same reason: feeding a machine-read emotion into the system
that tracks the user's actual reported mood is a deliberate wiring
decision for later, not something a stub should do silently.
"""

from typing import Dict, Optional

try:

    _SPEECHBRAIN_AVAILABLE = True
except Exception:
    _SPEECHBRAIN_AVAILABLE = False


class EmotionHearer:
    """Best-effort vocal emotion reading. Use get_emotion_hearer()."""

    def __init__(self):
        self._model = None
        if _SPEECHBRAIN_AVAILABLE:
            try:
                from speechbrain.inference.interfaces import foreign_class

                self._model = foreign_class(
                    source="speechbrain/emotion-recognition-wav2vec2-IEMOCAP",
                    pymodule_file="custom_interface.py",
                    classname="CustomEncoderWav2vec2Classifier",
                )
            except Exception:
                self._model = None

    def is_available(self) -> bool:
        return self._model is not None

    def read_emotion(self, audio_path: str) -> Optional[Dict]:
        """Takes a path to an audio file (this model's interface reads
        from disk, not raw samples) and returns {"label": str,
        "confidence": float}, or None - no model installed, bad path,
        or any failure all collapse to the same None. Never fabricates
        an emotion when the model isn't there."""
        if not self.is_available() or not audio_path:
            return None
        try:
            _, score, _, label = self._model.classify_file(audio_path)
            return {
                "label": str(label[0]) if isinstance(label, (list, tuple)) else str(label),
                "confidence": round(float(score[0]) if hasattr(score, "__getitem__") else float(score), 3),
            }
        except Exception:
            return None


_emotion_hearer: Optional[EmotionHearer] = None


def get_emotion_hearer() -> EmotionHearer:
    global _emotion_hearer
    if _emotion_hearer is None:
        _emotion_hearer = EmotionHearer()
    return _emotion_hearer
