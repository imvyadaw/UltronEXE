"""
Edge TTS backend
==================
Microsoft Edge neural voices (en-IN-NeerjaNeural / en-IN-PrabhatNeural /
en-US-AvaNeural / etc - see config.TTS_VOICE), via the `edge_tts` Python
library. This module is synthesis-only (text -> mp3 file); the
streaming/caching/playback pipeline that used to live directly in
tts_engine.py now lives there as a thin orchestrator that calls whichever
backend (this one, gtts_tts.py, or pyttsx_tts.py) config.TTS_ENGINE picks.

NOTE ON THE FILENAME: this module is voice/tts/edge_tts.py, i.e. it
shares its name with the third-party `edge_tts` PyPI package it wraps.
That's safe here because Python 3's imports are absolute by default -
`import edge_tts` below resolves against sys.path (site-packages), not
against this package's own directory, since voice/tts/ itself is never
added to sys.path. Do not rename this to something that WOULD end up on
sys.path (e.g. don't move it to the project root) without renaming the
import.
"""

import asyncio
import threading
from typing import Optional

try:
    import edge_tts

    HAS_EDGE_TTS = True
except ImportError:
    HAS_EDGE_TTS = False

from config import TTS_VOICE, TTS_RATE, TTS_PITCH, TTS_VOLUME
from core.logger import get_logger

logger = get_logger("edge_tts")


def _fmt_signed(value: int, unit: str) -> str:
    return f"+{value}{unit}" if value >= 0 else f"{value}{unit}"


class EdgeTTSBackend:
    """Synthesis-only Edge TTS backend - runs its own background asyncio
    loop so callers never have to think about asyncio.run() colliding
    with any other event loop in the app."""

    name = "edge"

    def __init__(
        self,
        voice: str = TTS_VOICE,
        rate: int = TTS_RATE,
        pitch: int = TTS_PITCH,
        volume: int = TTS_VOLUME,
    ):
        if not HAS_EDGE_TTS:
            raise RuntimeError("edge-tts not installed - run: pip install edge-tts")
        self.voice = voice
        self.rate = _fmt_signed(rate, "%")
        self.pitch = _fmt_signed(pitch, "Hz")
        self.volume = _fmt_signed(volume, "%")
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._loop_thread: Optional[threading.Thread] = None
        self._start_loop()

    def _start_loop(self):
        ready = threading.Event()

        def runner():
            self._loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._loop)
            ready.set()
            self._loop.run_forever()

        self._loop_thread = threading.Thread(target=runner, daemon=True, name="ultron-edge-tts-loop")
        self._loop_thread.start()
        ready.wait(timeout=5.0)

    def _run_coro(self, coro, timeout: Optional[float] = None):
        if self._loop is None:
            return None
        future = asyncio.run_coroutine_threadsafe(coro, self._loop)
        return future.result(timeout=timeout)

    async def _synthesize_async(self, text: str, out_path: str, voice: str):
        communicate = edge_tts.Communicate(text, voice, rate=self.rate, pitch=self.pitch, volume=self.volume)
        await communicate.save(out_path)

    def synthesize(self, text: str, out_path: str, timeout: float = 4.0, voice: Optional[str] = None) -> Optional[str]:
        """Render `text` to an mp3 file at `out_path`. Returns out_path on
        success, None on failure (caller falls through to the next
        configured TTS engine - gtts, then pyttsx3 - so this stays quiet
        instead of printing to the terminal every time). Timeout cut from
        the old 20s to 4s: a slow/failing Edge call used to block the
        whole reply for up to 20 seconds before handing off to a
        fallback that would have worked instantly.

        `voice`, if given, overrides self.voice for this single call only
        (self.voice/set_voice() are unchanged) - used by tts_engine.py to
        drop in TTS_VOICE_HINDI for a Devanagari sentence without
        permanently switching the backend's configured voice."""
        try:
            self._run_coro(self._synthesize_async(text, out_path, voice or self.voice), timeout=timeout)
            return out_path
        except Exception as e:
            logger.debug("Edge TTS synth failed, falling back: %s", e)
            return None

    def set_voice(self, voice: str):
        self.voice = voice

    def set_rate(self, rate_percent: int):
        self.rate = _fmt_signed(max(-50, min(100, rate_percent)), "%")

    def set_pitch(self, pitch_hz: int):
        self.pitch = _fmt_signed(max(-50, min(50, pitch_hz)), "Hz")

    def set_volume(self, volume_percent: int):
        self.volume = _fmt_signed(max(-50, min(50, volume_percent)), "%")


async def list_voices():
    """List all available Edge TTS voices."""
    voices = await edge_tts.list_voices()
    return voices


_instance: Optional[EdgeTTSBackend] = None


def get_edge_backend() -> EdgeTTSBackend:
    global _instance
    if _instance is None:
        _instance = EdgeTTSBackend()
    return _instance
