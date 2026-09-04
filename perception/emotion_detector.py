"""
Emotion Detector (Phase 22 - Perception)
=========================================
Composite affect signal, combining whatever inputs are available for a
given call rather than requiring all of them:

  - text sentiment (voice/emotion_detection.py's EmotionDetector,
    keyword-based) - works off any transcript, always available
  - acoustic voice emotion (same module, analyze_audio) - needs raw
    audio, best-effort
  - facial expression (PHASE_18_3_VISION_SYSTEM/EYES/emotion_read.py) -
    needs a camera frame and the optional `fer` package; honest stub
    returns None if unavailable, this module respects that
  - vocal-model emotion (PHASE_18_4_VOICE_SYSTEM/EARS/emotion_hear.py) -
    needs an audio file path and the optional `speechbrain` package;
    same honest-stub behavior

Both EYES/emotion_read.py and EARS/emotion_hear.py explicitly left
"feeding a machine-read emotion into memory/emotional_memory.py" as a
deliberate wiring decision for later rather than doing it themselves.
This module is that decision: record_if_confident() writes a composite
reading to emotional_memory only when at least two signals agree, never
off a single heuristic alone - the whole point of keeping that as a
separate opt-in step.
"""

import time
from collections import Counter
from typing import Dict, List, Optional

from core.logger import get_logger

logger = get_logger("ultron.perception.emotion_detector")

AGREEMENT_THRESHOLD = 2  # minimum number of signals that must agree before logging to emotional_memory


class EmotionDetector:
    def detect(
        self, text: Optional[str] = None, audio=None, audio_path: Optional[str] = None, frame=None, record: bool = False
    ) -> Dict:
        """Runs every signal that has an input to work with. Every arg
        is optional - pass only what you have (a transcript, raw mic
        audio, a saved audio file, a camera frame)."""
        signals: List[Dict] = []

        if text:
            r = self._text_sentiment(text)
            if r:
                signals.append({"source": "text", **r})
        if audio is not None:
            r = self._acoustic_emotion(audio)
            if r:
                signals.append({"source": "voice_acoustic", **r})
        if audio_path:
            r = self._vocal_model_emotion(audio_path)
            if r:
                signals.append({"source": "voice_model", **r})
        if frame is not None:
            r = self._facial_emotion(frame)
            if r:
                signals.append({"source": "face", **r})

        composite = self._combine(signals)
        data = {"signals": signals, "composite": composite}

        if record and composite:
            self._record_if_confident(signals, composite)

        return self._emit(data)

    # -- individual signals, each best-effort ---------------------------
    def _text_sentiment(self, text: str) -> Optional[Dict]:
        try:
            from voice.emotion_detection import get_emotion_detector as get_voice_emotion_detector

            return get_voice_emotion_detector().analyze_text_sentiment(text)
        except Exception as exc:
            logger.debug(f"emotion_detector: text sentiment unavailable: {exc}")
            return None

    def _acoustic_emotion(self, audio) -> Optional[Dict]:
        try:
            from voice.emotion_detection import get_emotion_detector as get_voice_emotion_detector

            return get_voice_emotion_detector().analyze_audio(audio)
        except Exception as exc:
            logger.debug(f"emotion_detector: acoustic emotion unavailable: {exc}")
            return None

    def _vocal_model_emotion(self, audio_path: str) -> Optional[Dict]:
        try:
            from ears.emotion_hear import get_emotion_hearer

            hearer = get_emotion_hearer()
            if not hearer.is_available():
                return None
            return hearer.read_emotion(audio_path)
        except Exception as exc:
            logger.debug(f"emotion_detector: vocal-model emotion unavailable: {exc}")
            return None

    def _facial_emotion(self, frame) -> Optional[Dict]:
        try:
            from eyes.emotion_read import get_emotion_reader

            reader = get_emotion_reader()
            if not reader.is_available():
                return None
            return reader.read_emotion(frame)
        except Exception as exc:
            logger.debug(f"emotion_detector: facial emotion unavailable: {exc}")
            return None

    # -- combine ----------------------------------------------------------
    def _normalize_label(self, signal: Dict) -> Optional[str]:
        """Different sources use different field names for their verdict
        (emotion vs sentiment) - normalize to one label per signal before
        voting."""
        return signal.get("emotion") or signal.get("sentiment")

    def _combine(self, signals: List[Dict]) -> Optional[Dict]:
        """Plain majority vote over each signal's reported label,
        deliberately simple - this is a hint, not a clinical measure,
        same standard the rest of this codebase holds emotion readings
        to (see voice/emotion_detection.py, EYES/EARS stubs)."""
        labels = [self._normalize_label(s) for s in signals]
        labels = [l for l in labels if l]
        if not labels:
            return None
        counts = Counter(labels)
        label, count = counts.most_common(1)[0]
        return {"emotion": label, "agreement": count, "of_signals": len(labels)}

    def _record_if_confident(self, signals: List[Dict], composite: Dict) -> None:
        if composite.get("agreement", 0) < AGREEMENT_THRESHOLD:
            return
        try:
            from memory.emotional_memory import EmotionalMemory

            EmotionalMemory().log_mood(
                emotion=composite["emotion"],
                intensity=3,
                note=f"perception composite from {composite['of_signals']} signal(s)",
            )
        except Exception as exc:
            logger.debug(f"emotion_detector: could not log to emotional_memory: {exc}")

    # -- emit ----------------------------------------------------------
    def _emit(self, data: Dict) -> Dict:
        event = {"modality": "emotion", "timestamp": time.time(), "data": data, "source": "emotion_detector"}
        try:
            from core.event_bus import get_event_bus

            get_event_bus().emit("perception.emotion", **event)
        except Exception:
            from core.error_trace import log_swallowed as _lsw

            _lsw("perception.emotion_detector._emit")
        return event


_detector: Optional[EmotionDetector] = None


def get_emotion_detector() -> EmotionDetector:
    global _detector
    if _detector is None:
        _detector = EmotionDetector()
    return _detector
