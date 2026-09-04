"""
Backward-compat shim
=====================
This module was renamed to voice/stt/whisper_stt.py as part of Phase 9's
per-engine file layout (google_stt.py, vosk_stt.py, whisper_stt.py).
Kept here re-exporting everything from the new location so any external
code still doing `from voice.stt import local_whisper` or
`from voice.stt.local_whisper import transcribe_audio_data` keeps working
unchanged. New code should import voice.stt.whisper_stt directly.
"""

from voice.stt.whisper_stt import (  # noqa: F401
    is_available,
    last_error,
    transcribe_audio_data,
    MODEL_DIR,
    HAS_FASTER_WHISPER,
)
