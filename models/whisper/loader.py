"""
Whisper loader
==============
Speech-to-text via Groq's hosted whisper-large-v3, using the same
GROQ_API_KEY already required for the main chat client - no multi-gigabyte
model weights to bundle or download, unlike a locally-run Whisper would
need. This is a cloud backend for one-off audio *file* transcription
(e.g. a voice note someone hands Ultron). For live mic input, see
voice/stt/stt_engine.py instead - it already hybrid-routes between
Google's cloud STT and voice/stt/local_whisper.py's genuinely offline
local Whisper model, the same way ai/ai_router.py splits cloud/local
for the LLM brain.
"""

from typing import Dict

from groq import Groq

from config import GROQ_API_KEY


class WhisperTranscriber:
    """Audio-file transcription via Groq's cloud-hosted Whisper."""

    def __init__(self, model: str = "whisper-large-v3"):
        self.model = model
        self._client = Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None

    def transcribe(self, file_path: str, language: str = None) -> Dict:
        """Transcribe an audio file (wav/mp3/m4a/etc, <=25MB) to text."""
        if not self._client:
            return {"error": "GROQ_API_KEY not set - see config.py's diagnose_env()"}
        try:
            with open(file_path, "rb") as f:
                kwargs = {"file": (file_path, f.read()), "model": self.model}
                if language:
                    kwargs["language"] = language
                result = self._client.audio.transcriptions.create(**kwargs)
            return {"text": result.text}
        except FileNotFoundError:
            return {"error": f"Audio file not found: {file_path}"}
        except Exception as e:
            return {"error": str(e)}


def load(model: str = "whisper-large-v3") -> WhisperTranscriber:
    """Return a WhisperTranscriber. Does not raise if GROQ_API_KEY is
    missing - the error surfaces on the first transcribe() call instead,
    matching models/ollama/loader.py's "connect lazily" style."""
    return WhisperTranscriber(model=model)
