"""
gTTS backend
=============
Google Translate's text-to-speech, via the `gTTS` Python library. Second
choice after Edge TTS (config.TTS_ENGINE_FALLBACK) - not as natural
sounding as Edge's neural voices, but supports more languages out of the
box, including Hindi (config.GTTS_LANG="hi") which pairs naturally with
voice/stt/vosk_stt.py's Hindi STT model for a fully Hindi voice loop
(minus the STT/TTS network hop, since both gTTS and Google STT need
internet - use pyttsx_tts.py + vosk_stt.py together for a fully offline
Hindi round-trip instead).

Needs: pip install gTTS
"""

from typing import Optional

try:
    from gtts import gTTS

    HAS_GTTS = True
except ImportError:
    HAS_GTTS = False

from config import GTTS_LANG
from core.logger import get_logger

logger = get_logger("gtts_tts")


class GTTSBackend:
    """Synthesis-only gTTS backend - gTTS itself is synchronous/blocking
    (a plain HTTP request under the hood), so no background event loop
    is needed here unlike edge_tts.py."""

    name = "gtts"

    def __init__(self, lang: str = GTTS_LANG):
        if not HAS_GTTS:
            raise RuntimeError("gTTS not installed - run: pip install gTTS")
        self.lang = lang

    def synthesize(self, text: str, out_path: str, timeout: float = 4.0, lang: Optional[str] = None) -> Optional[str]:
        """Render `text` to an mp3 file at `out_path`. Returns out_path on
        success, None on failure (caller falls through to the next
        configured TTS engine, typically pyttsx3). `timeout` used to be
        accepted but never actually applied - gTTS.save() made a plain
        network call with no cap, so a slow/hanging connection could
        block a reply indefinitely instead of failing over quickly.

        `lang`, if given, overrides self.lang for this single call only -
        used by tts_engine.py to force GTTS_LANG_HINDI ("hi") for a
        Devanagari sentence even when self.lang is "en", instead of
        permanently switching the backend's configured language."""
        effective_lang = lang or self.lang
        try:
            try:
                tts = gTTS(text=text, lang=effective_lang, timeout=timeout)
            except TypeError:
                # Older gTTS versions don't accept `timeout` - fall back
                # to the no-timeout constructor rather than crashing.
                tts = gTTS(text=text, lang=effective_lang)
            tts.save(out_path)
            return out_path
        except Exception as e:
            logger.debug("gTTS synth failed, falling back: %s", e)
            return None

    def set_lang(self, lang: str):
        self.lang = lang


_instance: Optional[GTTSBackend] = None


def get_gtts_backend() -> GTTSBackend:
    global _instance
    if _instance is None:
        _instance = GTTSBackend()
    return _instance
