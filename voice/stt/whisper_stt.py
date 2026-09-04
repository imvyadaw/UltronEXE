"""
Local Whisper STT backend
===========================
Fully local speech-to-text via faster-whisper (CTranslate2-based, runs
fine on CPU, no GPU needed). This is the file voice/stt/local_whisper.py
used to be (kept there now as a thin backward-compat shim, since a couple
of other modules may still import it by that name) - moved/renamed to
whisper_stt.py to match the rest of the Phase 9 engine-per-file layout
(google_stt.py, vosk_stt.py).

stt_engine.py routes here whenever there's no internet (or
config.STT_MODE == "local"), so wake word detection and command
transcription both keep working with zero network access.

Model weights (config.WHISPER_LOCAL_MODEL - default "base", ~140MB) are
auto-downloaded from Hugging Face and cached under
storage/cache/models/whisper/ the first time this runs. That first
download needs internet; after that, this module never touches the
network again.

Needs: pip install faster-whisper
"""

import io
from pathlib import Path
from typing import Optional

try:
    from faster_whisper import WhisperModel

    HAS_FASTER_WHISPER = True
    _IMPORT_ERROR = None
except ImportError as e:
    # faster-whisper (or a sub-dependency) genuinely not installed.
    HAS_FASTER_WHISPER = False
    _IMPORT_ERROR = str(e)
except Exception as e:
    # faster-whisper pulls in ctranslate2 -> torch, and on Windows a
    # broken/incomplete torch install fails with OSError (e.g. WinError
    # 1114, "DLL initialization routine failed" on torch's c10.dll) -
    # not ImportError. Left uncaught, that OSError propagates straight
    # out of this module, out of voice/__init__.py, and kills the whole
    # voice subsystem instead of just Whisper - stt_engine.py never gets
    # the chance to fall back to Vosk/Google. Catching it here and
    # falling back to HAS_FASTER_WHISPER = False lets that fallback work
    # the way it was designed to.
    HAS_FASTER_WHISPER = False
    _IMPORT_ERROR = str(e)

from config import CACHE_DIR, WHISPER_LOCAL_MODEL, STT_LANGUAGE
from core.logger import get_logger

logger = get_logger("whisper_stt")

MODEL_DIR = Path(CACHE_DIR) / "models" / "whisper"

_model_instance = None
_load_failed = False
_load_error = None


def _get_model():
    """Lazy-load the model once per process - loading takes a couple
    seconds, not something to redo on every single utterance."""
    global _model_instance, _load_failed, _load_error
    if _model_instance is not None:
        return _model_instance
    if _load_failed:
        return None
    if not HAS_FASTER_WHISPER:
        _load_failed = True
        _load_error = (
            f"faster-whisper unavailable ({_IMPORT_ERROR}) - " "run: pip install faster-whisper"
            if _IMPORT_ERROR
            else "faster-whisper not installed - run: pip install faster-whisper"
        )
        logger.warning("Local Whisper disabled at import time: %s", _load_error)
        return None
    try:
        MODEL_DIR.mkdir(parents=True, exist_ok=True)
        # int8 compute type keeps this fast and light on CPU-only
        # machines - no GPU requirement.
        _model_instance = WhisperModel(
            WHISPER_LOCAL_MODEL,
            device="cpu",
            compute_type="int8",
            download_root=str(MODEL_DIR),
        )
        logger.info("Local Whisper model '%s' loaded from %s.", WHISPER_LOCAL_MODEL, MODEL_DIR)
        return _model_instance
    except Exception as e:
        logger.warning("Local Whisper model failed to load (%s) - offline STT unavailable.", e)
        _load_failed = True
        _load_error = str(e)
        return None


def is_available() -> bool:
    return _get_model() is not None


def last_error() -> Optional[str]:
    return _load_error


def transcribe_audio_data(audio) -> Optional[str]:
    """Transcribe an sr.AudioData object fully offline. Returns None if
    the local model isn't available or nothing intelligible was heard."""
    model = _get_model()
    if model is None:
        return None
    try:
        wav_bytes = io.BytesIO(audio.get_wav_data())
        lang = STT_LANGUAGE.split("-")[0]  # "en-IN" -> "en"
        # Whisper is multilingual and auto-detects the spoken language
        # per utterance when language=None - previously this always
        # forced "en" (from the "en-IN" default), so any Hindi spoken
        # offline was silently mis-heard as English. Only force a
        # language if STT_LANGUAGE was deliberately set to something
        # other than the shipped default, so a Hindi/English/Hinglish
        # user gets real auto-detection out of the box.
        detect_lang = None if lang == "en" else lang
        segments, _info = model.transcribe(wav_bytes, language=detect_lang, beam_size=1)
        text = " ".join(seg.text.strip() for seg in segments).strip()
        return text or None
    except Exception as e:
        logger.info("Local Whisper transcription failed: %s", e)
        return None
