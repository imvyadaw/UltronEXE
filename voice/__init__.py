"""Voice subsystem (Phase 9: multi-engine voice stack).

    tts/        - text-to-speech: edge_tts.py (neural, default),
                  gtts_tts.py, pyttsx_tts.py (offline) - tts_engine.py
                  orchestrates all three with a fallback chain.
    stt/        - speech-to-text: google_stt.py (cloud), whisper_stt.py
                  (offline), vosk_stt.py (offline, Hindi-capable) -
                  stt_engine.py orchestrates all three.
    wakeword/   - wake word detection: detector.py (openWakeWord,
                  real-time streaming, default), wakeword.py (legacy
                  STT-based rolling-phrase approach, used as a fallback).
    microphone/ - microphone.py (discrete listen_once(), for commands),
                  stream.py (continuous raw-PCM streaming, for the
                  openWakeWord detector).
    audio/      - processor.py: shared audio-format/resampling helpers.

get_wakeword_detector() below is engine-selecting (config.WAKE_WORD_ENGINE)
- see voice/wakeword/wakeword.py for the actual selection logic.
"""

# BUG FIXED: get_voice/get_stt/get_wakeword_detector were documented
# above as living in this file ("below") but were never actually
# defined or re-exported here - only in their own submodules
# (voice.tts.tts_engine, voice.stt.stt_engine, voice.wakeword.wakeword).
# `from voice import get_voice` (used by core/assistant.py's
# run_voice_typed() and run_listen()) therefore always raised
# ImportError. Both call sites wrap that import in a try/except and
# silently fall back to text-only mode on failure - so `--voice` and
# the default (no-flag / --listen) hands-free mode were quietly
# running as `--text` the entire time, with only a console warning
# hinting at it. Re-exporting the real implementations here fixes both.
from voice.tts.tts_engine import get_voice
from voice.stt.stt_engine import get_stt
from voice.wakeword.wakeword import get_wakeword_detector

__all__ = ["get_voice", "get_stt", "get_wakeword_detector"]
