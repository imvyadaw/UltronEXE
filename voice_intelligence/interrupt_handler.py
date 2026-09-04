"""
Interrupt handler (barge-in)
==============================
Watches the mic while voice/tts/tts_engine.py is speaking and stops
playback the moment the VAD sees real speech - "barge-in", the thing
that makes a voice assistant feel conversational instead of making the
user wait out a whole reply to interject.

voice/tts/tts_engine.py itself has no notion of being interrupted mid-
sentence (it plays sentence chunks to completion), so this module treats
it as a black box and works at the process level: start playback in the
background, poll the VAD, and on trigger call the same stop mechanism
tts_engine.py exposes for "stop talking" voice commands
(voice/voice_commands.py already wires that up for typed/spoken
"stop"/"quiet" commands - this reuses the identical stop path, just
triggered by VAD instead of a recognized command word).

Emits "interaction:barge_in" on the unified event bus so
full_duplex_engine.py (and anything else watching, e.g. the orb) can
react - drop the current TTS queue, cut to "listening" state, etc. -
without this module needing to know who's listening.
"""

import threading
import time
from typing import Callable, Optional

from core_integration.phase16_bridge import get_bridge
from voice_intelligence.voice_activity_detector import VoiceActivityDetector
from core.logger import get_logger

try:
    from voice.tts.tts_engine import get_voice

    HAS_TTS_HOOKS = True
except ImportError:
    HAS_TTS_HOOKS = False

try:
    from voice.microphone.stream import MicrophoneStream

    HAS_MIC_STREAM = True
except ImportError:
    HAS_MIC_STREAM = False

logger = get_logger("ultron.interaction.interrupt")

# How many consecutive speech frames while TTS is playing before we treat
# it as a genuine interruption rather than TTS bleeding into the mic
# (echo) - kept higher than VAD's own on-debounce since false positives
# here cut off Ultron's own sentence, which is more annoying than a
# slightly slower barge-in.
BARGE_IN_FRAMES = 4


class InterruptHandler:
    """Runs a background watcher thread for the duration of one TTS
    utterance (or a whole full-duplex session) and calls `on_interrupt`
    the moment sustained speech is detected while Ultron is talking."""

    def __init__(self, on_interrupt: Optional[Callable[[], None]] = None):
        self._vad = VoiceActivityDetector()
        self._on_interrupt = on_interrupt or self._default_interrupt
        self._thread: Optional[threading.Thread] = None
        self._stop_flag = threading.Event()
        self.enabled = HAS_TTS_HOOKS and HAS_MIC_STREAM

    def _default_interrupt(self) -> None:
        if HAS_TTS_HOOKS:
            get_voice().stop()
        get_bridge().events.emit("interaction:barge_in", source="vad")
        logger.info("Barge-in detected - TTS stopped")

    def start(self) -> bool:
        """Begin watching for barge-in. Safe to call even if the mic is
        already in use elsewhere for STT - MicrophoneStream is a
        separate raw PyAudio tap, same design voice/wakeword/detector.py
        relies on (see mic stream module docstring)."""
        if not self.enabled:
            return False
        if self._thread and self._thread.is_alive():
            return True

        self._stop_flag.clear()
        self._thread = threading.Thread(target=self._watch_loop, daemon=True)
        self._thread.start()
        return True

    def stop(self) -> None:
        self._stop_flag.set()
        if self._thread:
            self._thread.join(timeout=1.0)

    def _watch_loop(self) -> None:
        try:
            stream = MicrophoneStream()
        except Exception as e:
            logger.warning(f"Interrupt handler couldn't open mic stream: {e}")
            return

        stream.start()
        voice = get_voice() if HAS_TTS_HOOKS else None
        streak = 0
        try:
            for frame in stream.frames():
                if self._stop_flag.is_set():
                    break
                if voice is None or not voice.is_speaking():
                    # Nothing to interrupt right now - stay idle rather
                    # than busy-polling the VAD for no reason.
                    streak = 0
                    continue

                if self._vad.score_frame(frame):
                    streak += 1
                else:
                    streak = 0

                if streak >= BARGE_IN_FRAMES:
                    self._on_interrupt()
                    streak = 0
                    # Give TTS a moment to actually stop before re-arming,
                    # so the tail end of the cut-off audio doesn't
                    # immediately re-trigger.
                    time.sleep(0.3)
        except Exception as e:
            logger.warning(f"Interrupt watch loop ended: {e}")
        finally:
            try:
                stream.stop()
            except Exception:
                from core.error_trace import log_swallowed as _lsw

                _lsw("voice_intelligence.interrupt_handler._watch_loop")


_default_handler: Optional[InterruptHandler] = None


def get_interrupt_handler() -> InterruptHandler:
    global _default_handler
    if _default_handler is None:
        _default_handler = InterruptHandler()
    return _default_handler
