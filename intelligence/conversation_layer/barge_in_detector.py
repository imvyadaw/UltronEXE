"""
Barge-In Detector (Phase 20 - Conversation Layer)
==================================================
Decides whether incoming speech while the assistant is talking is a
genuine barge-in (the user deliberately interrupting) or noise/echo
that shouldn't cut the assistant off - and, when it is a real
barge-in, gives a rough classification of what kind (a correction,
a brand new request, or just generic overlap) so
conversation_engine.py can react appropriately.

Deliberately simple/heuristic, same spirit as risk_assessor.py in
Phase 19.8: a speech-confidence threshold, a minimum elapsed-time
guard against the assistant's own audio bleeding back into the mic
right as it starts talking, and a short cue-word list for
classifying real interruptions. This module only classifies - it
never decides what to actually do about a barge-in (ending the
assistant's turn is turn_manager.py's job, orchestrating the whole
exchange is conversation_engine.py's job). Stateless: no persistence,
same as relation_mapper.py in Phase 19.7.
"""

import threading
from typing import Dict, Optional

_instance: Optional["BargeInDetector"] = None
_instance_lock = threading.Lock()

BARGE_IN_TYPE_CORRECTION = "correction"
BARGE_IN_TYPE_NEW_REQUEST = "new_request"
BARGE_IN_TYPE_GENERIC = "generic"

# ignore speech in the first bit of the assistant's own turn - most
# likely the mic picking up the assistant's own audio starting, not
# an actual interruption
_ECHO_GUARD_SECONDS = 0.4

# below this speech-confidence, treat it as probable background noise
_MIN_SPEECH_CONFIDENCE = 0.55

# a partial transcript this short is too little to act on confidently
_MIN_PARTIAL_WORDS = 1

_CORRECTION_CUES = {"no", "wait", "actually", "stop", "not that", "i meant", "sorry", "hold on"}
_NEW_REQUEST_CUES = {"instead", "forget that", "never mind", "actually can you", "one more thing"}


class BargeInDetector:
    """(assistant_is_speaking, assistant_turn_started_at, incoming_signal, now)
    -> {"is_barge_in", "confidence", "barge_in_type", "reasons"}."""

    def detect(
        self, assistant_is_speaking: bool, assistant_turn_started_at: Optional[float], incoming_signal: Dict, now: float
    ) -> Dict:
        reasons = []
        if not assistant_is_speaking:
            reasons.append("assistant is not currently speaking - no barge-in possible")
            return {"is_barge_in": False, "confidence": 0.0, "barge_in_type": None, "reasons": reasons}

        speech_detected = bool(incoming_signal.get("speech_detected"))
        if not speech_detected:
            reasons.append("no speech detected in incoming signal")
            return {"is_barge_in": False, "confidence": 0.0, "barge_in_type": None, "reasons": reasons}

        elapsed = (now - assistant_turn_started_at) if assistant_turn_started_at else None
        if elapsed is not None and elapsed < _ECHO_GUARD_SECONDS:
            reasons.append(f"only {elapsed:.2f}s into assistant turn - likely echo, not a real barge-in")
            return {"is_barge_in": False, "confidence": 0.1, "barge_in_type": None, "reasons": reasons}

        speech_confidence = float(incoming_signal.get("speech_confidence", 0.0))
        partial_text = (incoming_signal.get("partial_text") or "").strip()
        word_count = len(partial_text.split())

        if speech_confidence < _MIN_SPEECH_CONFIDENCE:
            reasons.append(f"speech_confidence {speech_confidence:.2f} below threshold {_MIN_SPEECH_CONFIDENCE}")
            return {"is_barge_in": False, "confidence": speech_confidence, "barge_in_type": None, "reasons": reasons}

        if word_count < _MIN_PARTIAL_WORDS:
            reasons.append("partial transcript too short to act on")
            return {
                "is_barge_in": False,
                "confidence": speech_confidence * 0.5,
                "barge_in_type": None,
                "reasons": reasons,
            }

        confidence = speech_confidence
        reasons.append(f"speech_confidence {speech_confidence:.2f} clears threshold")
        if word_count >= 3:
            confidence = min(1.0, confidence + 0.1)
            reasons.append("partial transcript has enough words to be intentional speech")

        barge_in_type = self._classify_type(partial_text, reasons)
        return {
            "is_barge_in": True,
            "confidence": round(confidence, 3),
            "barge_in_type": barge_in_type,
            "reasons": reasons,
        }

    @staticmethod
    def _classify_type(partial_text: str, reasons) -> str:
        lowered = partial_text.lower()
        for cue in _NEW_REQUEST_CUES:
            if cue in lowered:
                reasons.append(f"matched new-request cue '{cue}'")
                return BARGE_IN_TYPE_NEW_REQUEST
        for cue in _CORRECTION_CUES:
            if lowered.startswith(cue) or f" {cue} " in f" {lowered} ":
                reasons.append(f"matched correction cue '{cue}'")
                return BARGE_IN_TYPE_CORRECTION
        reasons.append("no correction/new-request cue matched - generic overlap")
        return BARGE_IN_TYPE_GENERIC


def get_barge_in_detector() -> BargeInDetector:
    """Process-wide BargeInDetector singleton (stateless, shared for consistency)."""
    global _instance
    if _instance is None:
        with _instance_lock:
            if _instance is None:
                _instance = BargeInDetector()
    return _instance
