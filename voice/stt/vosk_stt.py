"""
Vosk STT backend (offline, Hindi-capable)
============================================
Fully offline speech-to-text via Vosk (https://alphacephei.com/vosk/) -
smaller and faster to start up than local Whisper (voice/stt/whisper_stt.py),
and has a dedicated Hindi model, which Whisper's/Google's Hindi accuracy
doesn't match as well. This is the engine voice/stt/stt_engine.py prefers
for Hindi (STT_LANGUAGE starting with "hi") when config.STT_MODE is "auto"
or "vosk" and a Hindi model is present.

Unlike Whisper, Vosk model weights are NOT auto-downloaded here - they're
40MB-1GB+ zips from https://alphacephei.com/vosk/models that need a manual
download + unzip into config.VOSK_MODEL_PATH_EN / VOSK_MODEL_PATH_HI.
Reasonable starting picks:
    English (small, ~40MB):  vosk-model-small-en-us-0.15
    Hindi   (~1GB):          vosk-model-hi-0.22
    Hindi   (small, ~50MB):  vosk-model-small-hi-0.22

Needs: pip install vosk
"""

import json
from pathlib import Path
from typing import Dict, Optional

try:
    import vosk

    vosk.SetLogLevel(-1)  # silence Vosk's own stderr logging
    HAS_VOSK = True
except ImportError:
    HAS_VOSK = False

from config import VOSK_MODEL_PATH_EN, VOSK_MODEL_PATH_HI
from core.logger import get_logger

logger = get_logger("vosk_stt")

_MODEL_PATHS: Dict[str, str] = {
    "en": VOSK_MODEL_PATH_EN,
    "hi": VOSK_MODEL_PATH_HI,
}

_models: Dict[str, object] = {}
_load_failed: Dict[str, bool] = {}
_load_errors: Dict[str, str] = {}


def _lang_key(language: str) -> str:
    """ "hi-IN" / "hi" -> "hi"; "en-IN" / "en-US" -> "en"; anything else
    falls back to "en" since that's the most likely to have a model."""
    short = language.split("-")[0].lower()
    return short if short in _MODEL_PATHS else "en"


def _get_model(language: str):
    key = _lang_key(language)
    if key in _models:
        return _models[key]
    if _load_failed.get(key):
        return None
    if not HAS_VOSK:
        _load_failed[key] = True
        _load_errors[key] = "vosk not installed - run: pip install vosk"
        return None

    model_path = Path(_MODEL_PATHS[key])
    if not model_path.exists() or not any(model_path.iterdir()):
        _load_failed[key] = True
        _load_errors[key] = (
            f"No Vosk model found at {model_path} - download one from "
            "https://alphacephei.com/vosk/models and unzip it there."
        )
        return None

    try:
        model = vosk.Model(str(model_path))
        _models[key] = model
        logger.info("Vosk '%s' model loaded from %s.", key, model_path)
        return model
    except Exception as e:
        logger.warning("Vosk model load failed for '%s' (%s).", key, e)
        _load_failed[key] = True
        _load_errors[key] = str(e)
        return None


def is_available(language: str = "en") -> bool:
    return _get_model(language) is not None


def last_error(language: str = "en") -> Optional[str]:
    return _load_errors.get(_lang_key(language))


def transcribe_audio_data(audio, language: str = "en") -> Optional[str]:
    """Transcribe an sr.AudioData object fully offline via Vosk. Returns
    None if no model is available for `language` or nothing intelligible
    was heard. `language` is typically config.STT_LANGUAGE, e.g. "hi-IN"."""
    model = _get_model(language)
    if model is None:
        return None
    try:
        sample_rate = int(audio.sample_rate)
        raw = audio.get_raw_data(convert_rate=sample_rate, convert_width=2)

        recognizer = vosk.KaldiRecognizer(model, sample_rate)
        recognizer.SetWords(False)
        recognizer.AcceptWaveform(raw)
        result = json.loads(recognizer.FinalResult())
        text = (result.get("text") or "").strip()
        return text or None
    except Exception as e:
        logger.info("Vosk transcription failed: %s", e)
        return None


def transcribe_pcm16(raw: bytes, sample_rate: int, language: str = "en") -> Optional[str]:
    """Same as transcribe_audio_data() but for raw 16-bit PCM bytes
    directly (e.g. straight from voice/microphone/stream.py), for callers
    that don't have an sr.AudioData wrapper handy."""
    model = _get_model(language)
    if model is None:
        return None
    try:
        recognizer = vosk.KaldiRecognizer(model, sample_rate)
        recognizer.AcceptWaveform(raw)
        result = json.loads(recognizer.FinalResult())
        text = (result.get("text") or "").strip()
        return text or None
    except Exception as e:
        logger.info("Vosk transcription failed: %s", e)
        return None
