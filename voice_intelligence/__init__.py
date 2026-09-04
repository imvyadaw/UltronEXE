"""
VOICE_INTELLIGENCE
====================
Continuous, multi-speaker voice interaction on top of Phase 16's
voice/ package (voice/microphone, voice/stt, voice/tts, voice/wakeword,
voice/speaker_recognition, voice/emotion_detection - all reused, none
replaced).

    voice_activity_detector.py - is someone talking right now, frame by
                                  frame (energy + zero-crossing rate,
                                  webrtcvad if installed).
    interrupt_handler.py       - barge-in: stop TTS mid-sentence the
                                  instant VAD sees real speech while
                                  Ultron is talking.
    full_duplex_engine.py      - wires VAD + interrupt_handler + the
                                  mic stream + STT/TTS into one
                                  listen-while-speaking conversation
                                  loop. The main entry point of this
                                  sub-package.
    speaker_diarization.py     - "who said that" - segments a stream
                                  into speaker turns using
                                  speaker_recognition.py's voiceprint
                                  features plus simple online clustering.
    emotion_analyzer.py        - fuses voice/emotion_detection.py's
                                  acoustic read with text-sentiment for
                                  one combined emotion estimate.
    custom_tts_engine.py       - a thin layer over voice/tts/tts_engine.py
                                  that maps an emotion/persona to
                                  concrete rate/pitch/voice settings.
    offline_voice_pipeline.py  - wakeword (openWakeWord) + STT
                                  (Vosk/local Whisper) + TTS (pyttsx3)
                                  chained with zero cloud calls, for
                                  when core.internet_monitor says we're
                                  offline.
"""
