"""
Voice Processor (Phase 22 - Perception)
========================================
One call in, one structured perception out: listen on the mic, transcribe
it (voice/stt/stt_engine.py, which already handles the cloud/offline
Hindi/English routing), best-effort identify the speaker
(voice/speaker_recognition.py) and read acoustic emotion
(voice/emotion_detection.py), then emit the whole thing as one
"perception.voice" event on core.event_bus instead of three separate
call sites each wiring their own bit.

This does not replace voice/wakeword or the always-listening pipeline
in PHASE_17_5_HUMAN_INTERACTION/VOICE_INTELLIGENCE/full_duplex_engine.py
- those own the "when to start listening" decision. This module is the
"given a listen turn happened, process everything about it in one
place" step, callable by either of them, or directly (e.g. from
action_pipeline as the "perceive_voice" capability).
"""

import time
from typing import Dict, Optional

from core.logger import get_logger

logger = get_logger("ultron.perception.voice_processor")


class VoiceProcessor:
    def __init__(self):
        pass

    def listen_and_process(
        self,
        timeout: Optional[float] = None,
        phrase_time_limit: Optional[float] = None,
        identify_speaker: bool = True,
        analyze_emotion: bool = True,
    ) -> Dict:
        """Blocking: listens once on the default mic and returns a full
        perception dict. Every sub-step is best-effort - a missing
        optional dependency degrades that one field to None rather than
        failing the whole read."""
        from voice.microphone.microphone import get_microphone

        mic = get_microphone()
        audio = mic.listen_once(timeout=timeout, phrase_time_limit=phrase_time_limit)

        if audio is None:
            return self._emit({"transcript": None, "heard": False}, ok=False)

        transcript = self._transcribe(audio)
        speaker = self._identify_speaker(audio) if identify_speaker else None
        emotion = self._analyze_emotion(audio, transcript) if analyze_emotion else None

        data = {
            "heard": True,
            "transcript": transcript,
            "speaker": speaker,
            "emotion": emotion,
        }
        return self._emit(data, ok=transcript is not None)

    def process_transcript(self, transcript: str) -> Dict:
        """For callers that already have text (e.g. typed input, or a
        wakeword pipeline that transcribed on its own) and just want the
        same normalized event shape + text-sentiment reading."""
        emotion = self._analyze_text_emotion(transcript)
        return self._emit({"heard": True, "transcript": transcript, "speaker": None, "emotion": emotion}, ok=True)

    # -- sub-steps, each best-effort ---------------------------------------
    def _transcribe(self, audio) -> Optional[str]:
        try:
            from voice.stt.stt_engine import get_stt

            return get_stt().transcribe_audio(audio)
        except Exception as exc:
            logger.debug(f"voice_processor: transcription unavailable: {exc}")
            return None

    def _identify_speaker(self, audio) -> Optional[Dict]:
        try:
            from voice.speaker_recognition import get_speaker_recognizer

            result = get_speaker_recognizer().identify(audio)
            return result if isinstance(result, dict) else None
        except Exception as exc:
            logger.debug(f"voice_processor: speaker id unavailable: {exc}")
            return None

    def _analyze_emotion(self, audio, transcript: Optional[str]) -> Optional[Dict]:
        try:
            from voice.emotion_detection import get_emotion_detector as get_voice_emotion_detector

            return get_voice_emotion_detector().analyze_audio(audio)
        except Exception as exc:
            logger.debug(f"voice_processor: acoustic emotion unavailable: {exc}")
        return self._analyze_text_emotion(transcript) if transcript else None

    def _analyze_text_emotion(self, transcript: Optional[str]) -> Optional[Dict]:
        if not transcript:
            return None
        try:
            from voice.emotion_detection import get_emotion_detector as get_voice_emotion_detector

            return get_voice_emotion_detector().analyze_text_sentiment(transcript)
        except Exception as exc:
            logger.debug(f"voice_processor: text sentiment unavailable: {exc}")
            return None

    # -- emit ----------------------------------------------------------
    def _emit(self, data: Dict, ok: bool) -> Dict:
        event = {"modality": "voice", "timestamp": time.time(), "data": data, "source": "voice_processor"}
        try:
            from core.event_bus import get_event_bus

            get_event_bus().emit("perception.voice", **event)
        except Exception:
            from core.error_trace import log_swallowed as _lsw

            _lsw("perception.voice_processor._emit")
        if not ok:
            return event
        try:
            from core.consciousness import get_consciousness

            get_consciousness().note_outcome(True, detail="voice perceived")
        except Exception:
            from core.error_trace import log_swallowed as _lsw

            _lsw("perception.voice_processor._emit")
        return event


_processor: Optional[VoiceProcessor] = None


def get_voice_processor() -> VoiceProcessor:
    global _processor
    if _processor is None:
        _processor = VoiceProcessor()
    return _processor
