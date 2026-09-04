"""
Full-duplex engine
=====================
The main entry point of VOICE_INTELLIGENCE - a listen-while-speaking
conversation loop, replacing main.py's default half-duplex pattern
(wake word -> listen -> think -> speak -> back to wake word, each step
blocking the next) with one where the mic never stops being watched:

    1. voice/wakeword (or offline_voice_pipeline.py) fires
    2. voice/stt/stt_engine.py transcribes the command
    3. the transcript is hexpr through PHASE_17_1's bridge.brain (or, if
       a request looks like it needs the swarm, PHASE_17_4's
       orchestrator - see _route()) to get a reply
    4. voice/tts speaks the reply *while* interrupt_handler.py's watcher
       is armed, so the user can barge in at any point
    5. on barge-in, the partial reply is abandoned and step 2 restarts
       immediately - no need to re-trigger the wake word for a follow-up

This module owns the loop and the wiring; it deliberately does not
reimplement STT/TTS/wake word/routing itself, only calls into the
existing pieces in order and reacts to interrupt_handler's callback.
run_forever() is meant to replace (or run alongside, on request) the
listen loop in main.py / core/assistant.py - it is opt-in, not a
monkeypatch of the existing loop.
"""

import threading
import time
from typing import Optional

from core_integration.phase16_bridge import get_bridge
from voice_intelligence.interrupt_handler import InterruptHandler
from core.logger import get_logger

logger = get_logger("ultron.interaction.full_duplex")


class FullDuplexEngine:
    """Owns one continuous listen/think/speak loop with barge-in.
    Construct one per run - it holds a running background thread and
    small pieces of turn state, not a shared singleton by default
    (get_engine() below provides the convenience singleton for
    callers that just want "the" engine)."""

    def __init__(self):
        self._bridge = get_bridge()
        self._interrupt = InterruptHandler(on_interrupt=self._handle_barge_in)
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._interrupted = threading.Event()

    def _handle_barge_in(self):
        self._interrupted.set()
        try:
            from voice.tts.tts_engine import get_voice

            get_voice().stop()
        except Exception:
            from core.error_trace import log_swallowed as _lsw

            _lsw("voice_intelligence.full_duplex_engine._handle_barge_in")
        self._bridge.events.emit("interaction:barge_in")

    def _listen_for_command(self) -> Optional[str]:
        try:
            from voice.microphone.microphone import get_microphone
            from voice.stt.stt_engine import get_stt
        except ImportError:
            logger.warning("voice.microphone/voice.stt unavailable")
            return None
        try:
            audio = get_microphone().listen_once()
            if audio is None:
                return None
            return get_stt().transcribe_audio(audio)
        except Exception as e:
            logger.warning(f"Full-duplex listen failed: {e}")
            return None

    def _route(self, text: str) -> str:
        """Same "cheap local routing first" philosophy as
        ai/local_router.py - only reach for the multi-agent swarm when
        the request clearly needs decomposition across specialists."""
        swarm_hint_words = ("then", "and also", "at the same time", "meanwhile")
        if any(w in text.lower() for w in swarm_hint_words):
            try:
                from multi_agent_swarm.agent_orchestrator import get_orchestrator

                summary = get_orchestrator().handle_request(text)
                if isinstance(summary, dict) and summary.get("subtasks"):
                    parts = []
                    for t in summary["subtasks"]:
                        r = t.get("result", {})
                        parts.append(str(r.get("result", r.get("error", r))))
                    return " ".join(parts) or "Done."
            except Exception as e:
                logger.debug(f"Swarm routing skipped, falling back to brain: {e}")
        return self._bridge.brain.chat(text)

    def _speak(self, text: str) -> None:
        try:
            from voice.tts.tts_engine import get_voice

            get_voice().speak(text, blocking=True)
        except Exception as e:
            logger.warning(f"Full-duplex speak failed: {e}")

    def run_once(self) -> Optional[str]:
        """One listen -> think -> speak turn. Returns the reply text (or
        None if nothing was understood / the turn was interrupted before
        a reply was produced)."""
        self._interrupted.clear()
        self._interrupt.start()

        text = self._listen_for_command()
        if not text:
            return None

        self._bridge.events.emit("interaction:heard", text=text)
        reply = self._route(text)

        if self._interrupted.is_set():
            # The user started talking again before we even got to
            # speak - skip straight to listening for the follow-up
            # instead of speaking a reply nobody's waiting for.
            return reply

        self._bridge.events.emit("interaction:replying", text=reply)
        self._speak(reply)
        return reply

    def _loop(self) -> None:
        logger.info("Full-duplex engine started")
        while self._running:
            try:
                self.run_once()
            except Exception as e:
                logger.warning(f"Full-duplex turn failed, continuing: {e}")
                time.sleep(0.5)

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        self._interrupt.stop()
        if self._thread:
            self._thread.join(timeout=2.0)
        logger.info("Full-duplex engine stopped")


_engine: Optional[FullDuplexEngine] = None


def get_engine() -> FullDuplexEngine:
    global _engine
    if _engine is None:
        _engine = FullDuplexEngine()
    return _engine
