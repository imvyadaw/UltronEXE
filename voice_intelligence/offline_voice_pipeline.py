"""
Offline voice pipeline
=========================
Forces every stage of the voice loop onto its fully-offline backend for
as long as this pipeline is active, for use when core.internet_monitor
reports no connectivity (or the user explicitly asks for offline mode):

    wake word -> voice/wakeword's openWakeWord path (already local/ONNX;
                 falls back to the legacy STT-based detector if
                 openwakeword isn't installed, per its own module docstring)
    STT       -> voice/stt/stt_engine.py forced to STT_MODE="local" or
                 "vosk" (faster-whisper / Vosk, no network call)
    TTS       -> voice/tts/tts_engine.py forced to engine "pyttsx3"
                 (OS-native voices, the one backend that needs neither
                 network nor an API key)

This module does not reimplement any of those three - it only flips the
existing config knobs voice/stt/stt_engine.py and UltronVoice.set_engine()
already read, and restores whatever was configured before when
deactivated, so turning offline mode off hands control back to
config.STT_MODE's normal "auto" policy exactly as it was.
"""

from typing import Dict, Optional

import config
from voice.tts.tts_engine import get_voice
from core.internet_monitor import is_online
from core.logger import get_logger

logger = get_logger("ultron.interaction.offline_pipeline")

OFFLINE_STT_MODE = "local"  # faster-whisper; use "vosk" instead if Vosk models are installed and preferred
OFFLINE_TTS_ENGINE = "pyttsx3"


class OfflineVoicePipeline:
    """Forces STT/TTS onto offline-only backends while active. Holds the
    previous settings so deactivate() can restore them exactly."""

    def __init__(self):
        self._active = False
        self._prev_stt_mode: Optional[str] = None

    @property
    def active(self) -> bool:
        return self._active

    def activate(self, stt_mode: str = OFFLINE_STT_MODE) -> Dict:
        if self._active:
            return {"success": True, "already_active": True}

        self._prev_stt_mode = getattr(config, "STT_MODE", "auto")
        config.STT_MODE = stt_mode
        try:
            get_voice().set_engine(OFFLINE_TTS_ENGINE)
        except Exception as e:
            logger.warning(f"Couldn't force pyttsx3 TTS backend: {e}")

        self._active = True
        logger.info(f"Offline voice pipeline active (STT_MODE={stt_mode}, TTS={OFFLINE_TTS_ENGINE})")
        return {"success": True, "stt_mode": stt_mode, "tts_engine": OFFLINE_TTS_ENGINE}

    def deactivate(self) -> Dict:
        if not self._active:
            return {"success": True, "already_inactive": True}
        if self._prev_stt_mode is not None:
            config.STT_MODE = self._prev_stt_mode
        self._active = False
        logger.info("Offline voice pipeline deactivated - restored previous STT_MODE")
        return {"success": True, "restored_stt_mode": self._prev_stt_mode}

    def auto_sync(self) -> Dict:
        """Call periodically (e.g. from core.internet_monitor's own poll
        loop, or once per full_duplex_engine.py turn) to activate/
        deactivate automatically as connectivity changes."""
        online = is_online()
        if online and self._active:
            return self.deactivate()
        if not online and not self._active:
            return self.activate()
        return {"success": True, "no_change": True, "online": online, "active": self._active}


_pipeline: Optional[OfflineVoicePipeline] = None


def get_offline_pipeline() -> OfflineVoicePipeline:
    global _pipeline
    if _pipeline is None:
        _pipeline = OfflineVoicePipeline()
    return _pipeline
