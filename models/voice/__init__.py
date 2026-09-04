"""
models/voice/ - category namespace for speech models. Currently just
models/whisper/ (cloud Whisper transcription); re-exported here so
callers can do `from models.voice import whisper` without needing to
know it's the only voice model loader yet. models/whisper/ itself is
unchanged and still importable directly.

    from models.voice import whisper
    transcriber = whisper.WhisperTranscriber()
"""

from models.whisper import loader as whisper
from models.whisper.loader import WhisperTranscriber

__all__ = ["whisper", "WhisperTranscriber"]
