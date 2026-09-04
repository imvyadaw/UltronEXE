"""
pyttsx3 backend (offline)
============================
Fully offline text-to-speech via the OS's own voices - SAPI5 on Windows,
NSSpeechSynthesizer on macOS, espeak on Linux. Lower quality than Edge's
neural voices or gTTS, but needs zero setup and zero internet, so it's
the last link in config.TTS_ENGINE_FALLBACK - the one guaranteed to keep
Ultron talking even with no network at all.

Same synthesize(text, out_path) interface as edge_tts.py/gtts_tts.py
(via pyttsx3's own save_to_file(), producing a .wav instead of .mp3) so
tts_engine.py's orchestrator can treat all three backends uniformly for
caching/playback. speak_direct() is also exposed for a lower-latency path
that skips the file round-trip entirely, since pyttsx3 can talk straight
to the OS's audio output.

Needs: pip install pyttsx3
"""

import threading
from typing import Optional

try:
    import pyttsx3

    HAS_PYTTSX3 = True
except ImportError:
    HAS_PYTTSX3 = False

from config import TTS_RATE, TTS_VOLUME, PYTTSX_VOICE_HINT


class PyttsxBackend:
    """pyttsx3 is not safe to drive from multiple threads at once (its
    internal engine loop assumes single-threaded use), so every public
    method here takes self._lock - callers already going through
    tts_engine.py's single UltronVoice instance never hit contention,
    this is just a safety net for direct use."""

    name = "pyttsx3"

    def __init__(
        self, rate_percent: int = TTS_RATE, volume_percent: int = TTS_VOLUME, voice_hint: str = PYTTSX_VOICE_HINT
    ):
        if not HAS_PYTTSX3:
            raise RuntimeError("pyttsx3 not installed - run: pip install pyttsx3")
        self._lock = threading.Lock()
        self._engine = pyttsx3.init()
        # pyttsx3's rate is words-per-minute, not a percent offset like
        # edge-tts - map our -50..+100 percent knob onto a WPM range
        # around a ~180wpm "normal speaking rate" baseline.
        base_wpm = 180
        self._engine.setProperty("rate", int(base_wpm * (1 + rate_percent / 100.0)))
        volume = max(0.0, min(1.0, 0.5 + volume_percent / 100.0))
        self._engine.setProperty("volume", volume)
        if voice_hint:
            self._select_voice(voice_hint)

    def _select_voice(self, hint: str):
        try:
            for voice in self._engine.getProperty("voices"):
                if hint.lower() in (voice.name or "").lower():
                    self._engine.setProperty("voice", voice.id)
                    return
        except Exception:
            from core.error_trace import log_swallowed as _lsw

            _lsw("voice.tts.pyttsx_tts._select_voice")

    def list_voices(self):
        try:
            return [(v.id, v.name) for v in self._engine.getProperty("voices")]
        except Exception:
            return []

    def synthesize(self, text: str, out_path: str, timeout: float = None) -> Optional[str]:
        """Render `text` to a .wav file at `out_path` via pyttsx3's own
        save_to_file(), so tts_engine.py can cache/play it the same way
        as the edge/gtts mp3 outputs. `timeout` is accepted for interface
        parity with the other backends but unused - runAndWait() blocks
        until synthesis is actually done."""
        with self._lock:
            try:
                self._engine.save_to_file(text, out_path)
                self._engine.runAndWait()
                return out_path
            except Exception as e:
                print(f"pyttsx3 synth error: {e}")
                return None

    def speak_direct(self, text: str):
        """Skip the file round-trip and speak straight to the OS audio
        output - lower latency than synthesize()+play, but blocking and
        without tts_engine.py's sentence-pipelining/caching."""
        with self._lock:
            try:
                self._engine.say(text)
                self._engine.runAndWait()
            except Exception as e:
                print(f"pyttsx3 speak error: {e}")

    def stop(self):
        try:
            self._engine.stop()
        except Exception:
            from core.error_trace import log_swallowed as _lsw

            _lsw("voice.tts.pyttsx_tts.stop")


_instance: Optional[PyttsxBackend] = None


def get_pyttsx_backend() -> PyttsxBackend:
    global _instance
    if _instance is None:
        _instance = PyttsxBackend()
    return _instance
