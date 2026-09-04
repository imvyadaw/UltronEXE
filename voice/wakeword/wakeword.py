"""
Wake word detection
====================
Listens continuously for a trigger phrase ("Ultron") before treating
speech as a command. This is a simple STT-based approach (transcribe
short rolling phrases, check if the wake word is in them) rather than a
dedicated low-latency keyword-spotting engine (e.g. Porcupine) - good
enough for a personal assistant, at the cost of a little more latency
and needing an internet connection (same as voice/stt/).

If the wake word and the command are spoken together ("Ultron, open
Chrome"), the remaining text after the wake word is passed straight to
on_detected() as the command, so the user doesn't have to speak twice.
"""

import threading
from typing import Callable, Optional

from voice.microphone.microphone import get_microphone
from voice.stt.stt_engine import get_stt
from config import WAKE_WORDS, WAKE_PHRASE_TIME_LIMIT
from core.logger import get_logger

logger = get_logger("wakeword")


class WakeWordDetector:
    def __init__(self, wake_words=WAKE_WORDS):
        self.wake_words = tuple(w.lower() for w in wake_words)
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def _contains_wake_word(self, text: str) -> Optional[str]:
        """If text contains a wake word, return whatever comes after it
        (may be empty string if only the wake word was said)."""
        lowered = text.lower()
        for wake in self.wake_words:
            idx = lowered.find(wake)
            if idx != -1:
                remainder = text[idx + len(wake) :].strip(" ,.-")
                return remainder
        return None

    def listen_loop(self, on_detected: Callable[[str], None]):
        """Blocking loop: listens for the wake word, then calls
        on_detected(command_text). command_text may be "" if the user
        only said the wake word - the caller should then prompt for a
        follow-up command (see main.py's voice mode loop)."""
        mic = get_microphone()
        stt = get_stt()
        mic.calibrate()

        while not self._stop_event.is_set():
            try:
                audio = mic.listen_once(timeout=None, phrase_time_limit=WAKE_PHRASE_TIME_LIMIT)
                if audio is None or self._stop_event.is_set():
                    continue

                text = stt.transcribe_audio(audio)
                if not text:
                    continue

                remainder = self._contains_wake_word(text)
                if remainder is not None:
                    on_detected(remainder)
            except Exception as e:
                # A3: a single bad mic read, transient STT failure, or an
                # unexpected error inside on_detected used to propagate out
                # of this loop entirely - silently ending wake-word
                # listening (daemon thread) or crashing the whole app (main
                # thread, via run_listen()). Log and keep listening instead.
                if self._stop_event.is_set():
                    break
                logger.warning("Wake-word loop iteration failed, continuing: %s", e)

    def listen(self, on_detected: Callable[[str], None]):
        """Start listening for the wake word in a background thread."""
        self._stop_event.clear()
        self._thread = threading.Thread(target=self.listen_loop, args=(on_detected,), daemon=True)
        self._thread.start()

    def stop(self):
        self._stop_event.set()


_detector_instance: Optional[WakeWordDetector] = None


def get_legacy_wakeword_detector() -> WakeWordDetector:
    """The original STT-based detector - always available as long as
    voice/stt/ works, used as the fallback when openWakeWord (the Phase 9
    default) isn't installed or WAKE_WORD_ENGINE=stt is set explicitly."""
    global _detector_instance
    if _detector_instance is None:
        _detector_instance = WakeWordDetector()
    return _detector_instance


def get_wakeword_detector():
    """Engine-selecting factory - see config.WAKE_WORD_ENGINE. Returns
    voice/wakeword/detector.py's OpenWakeWordDetector by default (real-time,
    fully offline once its models are cached), falling back to this
    module's legacy STT-based WakeWordDetector if openwakeword isn't
    installed or WAKE_WORD_ENGINE=stt is set. Both expose the same
    listen(on_detected)/stop() interface, so callers (core/assistant.py)
    never need to know which one they got."""
    from config import WAKE_WORD_ENGINE

    if WAKE_WORD_ENGINE == "stt":
        return get_legacy_wakeword_detector()

    try:
        from voice.wakeword.detector import get_openwakeword_detector

        detector = get_openwakeword_detector()
        print("[Ultron] Wake word engine: openWakeWord (offline, no internet needed).")
        return detector
    except Exception as e:
        from core.logger import get_logger

        get_logger("wakeword").warning(
            "openWakeWord unavailable (%s) - falling back to legacy STT-based wake word detection.", e
        )
        # Printed (not just logged to file) so this doesn't go unnoticed -
        # this is the fallback that needs internet (voice/stt/google_stt.py),
        # which is the #1 cause of "wake word sometimes doesn't work" reports.
        print(
            "[Ultron] WARNING: openWakeWord not available (%s).\n"
            "         Falling back to the LEGACY wake word detector, which needs "
            "internet (Google STT).\n"
            "         Run: pip install openwakeword   then restart Ultron for fully "
            "offline wake word detection.\n"
            "         (Run scripts/check_voice_offline.py for a full diagnosis.)" % e
        )
        return get_legacy_wakeword_detector()
