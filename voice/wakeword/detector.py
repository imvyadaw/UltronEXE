"""
Wake word detector (openWakeWord)
===================================
Real-time streaming keyword spotter, replacing the STT-based "record a
short phrase, transcribe it, check if the wake word is in the text"
approach in voice/wakeword/wakeword.py (kept as the "stt" engine / legacy
fallback - see config.WAKE_WORD_ENGINE).

openWakeWord (https://github.com/dscripka/openWakeWord) runs a small ONNX
model over a continuous stream of 80ms audio frames and scores each frame
for wake-word likelihood - lower latency, fully offline once its models
are cached, and doesn't need a full STT round-trip just to notice its own
name. "hey_ultron" ships as one of openWakeWord's pretrained models.

Falls back automatically:
  - openwakeword not installed -> get_wakeword_detector() (voice/__init__.py)
    hands back the legacy STT-based WakeWordDetector instead.
  - PyAudio/mic stream unavailable at runtime -> raises, same as the
    legacy engine did, so callers' existing except-and-fall-back-to-typed-
    mode handling (core/assistant.py's run_listen) keeps working unchanged.

Unlike the legacy detector, a fired wake word here does NOT also capture
the rest of the sentence - openWakeWord only scores frames, it doesn't
transcribe them. on_detected() is always called with an empty string; the
caller (core/assistant.py) already handles that case (prompts "Yes, Sir?"
and does a separate mic listen for the actual command).
"""

import threading
import time
from collections import defaultdict, deque
from typing import Callable, List, Optional

try:
    import openwakeword
    from openwakeword.model import Model as OWWModel

    HAS_OPENWAKEWORD = True
except ImportError:
    HAS_OPENWAKEWORD = False

from config import (
    WAKE_WORD_MODELS,
    WAKE_WORD_MODELS_DIR,
    WAKE_WORD_THRESHOLD,
    WAKE_WORD_FRAME_MS,
    WAKE_WORD_SMOOTH_FRAMES,
    WAKE_WORD_MIC_GAIN,
)
from voice.microphone.stream import MicrophoneStream
from core.logger import get_logger

logger = get_logger("wakeword_detector")


def _resolve_model_paths(names) -> List[str]:
    """A configured name is either a pretrained openWakeWord model name
    (left as-is - the library resolves + downloads those itself) or a
    custom model dropped into voice/wakeword/models/ (resolved to a full
    path here, .onnx preferred over .tflite if both exist)."""
    resolved = []
    for name in names:
        onnx_path = WAKE_WORD_MODELS_DIR / f"{name}.onnx"
        tflite_path = WAKE_WORD_MODELS_DIR / f"{name}.tflite"
        if onnx_path.exists():
            resolved.append(str(onnx_path))
        elif tflite_path.exists():
            resolved.append(str(tflite_path))
        else:
            resolved.append(name)  # pretrained - let openwakeword resolve it
    return resolved


class OpenWakeWordDetector:
    """Streaming wake word detector. Same public interface (listen/stop)
    as voice/wakeword/wakeword.py's WakeWordDetector, so voice/__init__.py
    can hand back whichever engine is active without callers caring."""

    def __init__(
        self,
        model_names=WAKE_WORD_MODELS,
        threshold: float = WAKE_WORD_THRESHOLD,
    ):
        if not HAS_OPENWAKEWORD:
            raise RuntimeError(
                "openwakeword not installed - run: pip install openwakeword "
                "(or set WAKE_WORD_ENGINE=stt in .env to use the legacy "
                "STT-based detector instead)"
            )
        self.threshold = threshold
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._model: Optional["OWWModel"] = None
        self._model_names = list(model_names)
        # Debounce: once a model fires, ignore further frames for this
        # many seconds so one utterance doesn't fire on_detected() twice
        # while its score stays above threshold across consecutive frames.
        # (Mostly moot now that listen_loop restarts the mic fresh after
        # every fire, but kept as a safety net.)
        self._debounce_seconds = 0.75
        self._last_fire = {}
        # Rolling score average per wake word - smooths out single noisy
        # frames (a quiet/echo-y room can make one 80ms frame score high
        # or low almost at random). Firing on the *average* of the last
        # WAKE_WORD_SMOOTH_FRAMES frames instead of one raw frame means
        # we can safely run at a lower threshold (more sensitive, catches
        # it on the first try) without also picking up more false
        # positives from random noise.
        self._score_windows = defaultdict(lambda: deque(maxlen=max(1, WAKE_WORD_SMOOTH_FRAMES)))

    def _load_model(self):
        if self._model is not None:
            return self._model
        download_ok = True
        try:
            # First run downloads openWakeWord's small pretrained feature
            # + melspectrogram models to its own cache dir - needs
            # internet once, then works fully offline.
            openwakeword.utils.download_models()
        except Exception as e:
            download_ok = False
            logger.warning(
                "openwakeword.utils.download_models() failed (%s) - if this "
                "is the first run and there was no internet at the time, "
                "the wake word model may be missing/corrupt and detection "
                "will be unreliable (random-seeming misses or false "
                "triggers). Reconnect to the internet and restart to retry.",
                e,
            )
        wakeword_models = _resolve_model_paths(self._model_names)
        self._model = OWWModel(wakeword_models=wakeword_models, inference_framework="onnx")
        # Sanity check: run one silent frame through the model right away.
        # A freshly-broken/partial model tends to throw here or return an
        # empty dict, rather than failing loudly later mid-conversation -
        # catching it now, with a clear message, beats the user thinking
        # "it's just not hearing me" for days.
        try:
            import numpy as np

            probe = self._model.predict(np.zeros(1280, dtype=np.int16))
            if not probe:
                logger.warning(
                    "openWakeWord model loaded but returned no scores on a "
                    "test frame - model files are likely missing/corrupt. "
                    "Delete the openwakeword cache folder and restart with "
                    "internet on to force a clean re-download."
                )
            self._model.reset()
        except Exception as e:
            logger.warning("openWakeWord self-test frame failed: %s", e)
        logger.info(
            "openWakeWord loaded with models: %s (threshold=%.2f, smoothing=%d frames, "
            "gain=%.1fx, models_downloaded_ok=%s)",
            self._model_names,
            self.threshold,
            WAKE_WORD_SMOOTH_FRAMES,
            WAKE_WORD_MIC_GAIN,
            download_ok,
        )
        return self._model

    def listen_loop(self, on_detected: Callable[[str], None]):
        """Blocking loop: streams mic frames through the openWakeWord
        model and calls on_detected("") whenever any configured wake
        word's score crosses `threshold`.

        IMPORTANT: the mic stream is explicitly stopped before calling
        on_detected() and freshly restarted after it returns. on_detected
        is where the caller (core/assistant.py) transcribes the actual
        command AND speaks the reply - both take real time, during which
        we must NOT be holding the mic device open:
          - Two simultaneous open audio streams on the same input device
            (this wake-word stream + the separate command-transcription
            stream) can make the OS/driver flaky.
          - If left running, this stream keeps queuing frames the whole
            time ULTRON is thinking/replying (including picking up its
            own voice through the mic). Those stale queued frames would
            then have to be drained/processed before any NEW wake word
            could be heard - this is what caused the "gets stuck, not
            ready for the next command right after replying" symptom.
        stop() drains the queue, so start()-ing again right after
        on_detected() returns guarantees we resume on live audio only.
        """
        model = self._load_model()
        mic = MicrophoneStream(frame_ms=WAKE_WORD_FRAME_MS)
        try:
            while not self._stop_event.is_set():
                fired = False
                try:
                    mic.start()
                    for frame_bytes in mic.frames():
                        if self._stop_event.is_set():
                            break
                        import numpy as np

                        frame = np.frombuffer(frame_bytes, dtype=np.int16)
                        if WAKE_WORD_MIC_GAIN != 1.0:
                            # Most laptop/webcam mics record quietly enough that
                            # openWakeWord's model never sees a strong signal to
                            # score high on - boost it before scoring. Clip to
                            # int16 range so we don't wrap around into noise.
                            boosted = frame.astype(np.float32) * WAKE_WORD_MIC_GAIN
                            frame = np.clip(boosted, -32768, 32767).astype(np.int16)
                        predictions = model.predict(frame)
                        now = time.monotonic()
                        for wake_name, raw_score in predictions.items():
                            window = self._score_windows[wake_name]
                            window.append(raw_score)
                            score = sum(window) / len(window)
                            if score < self.threshold:
                                continue
                            if now - self._last_fire.get(wake_name, 0.0) < self._debounce_seconds:
                                continue
                            self._last_fire[wake_name] = now
                            logger.info(
                                "Wake word '%s' fired (smoothed_score=%.3f, raw=%.3f).",
                                wake_name,
                                score,
                                raw_score,
                            )
                            model.reset()
                            window.clear()
                            # Release the mic device BEFORE handing control to
                            # the caller (command transcription + TTS reply) -
                            # see docstring above.
                            mic.stop()
                            fired = True
                            try:
                                on_detected("")
                            except Exception as e:
                                # A3: on_detected() is where the caller does
                                # command capture (STT) + reply (TTS) - a
                                # failure there (mic disconnected mid-turn,
                                # transient STT/TTS error) used to propagate
                                # all the way out of listen_loop, ending wake
                                # word detection for the rest of the process.
                                # Log it and keep listening instead.
                                logger.warning("on_detected() raised, resuming wake-word listening: %s", e)
                            break  # re-enter the outer while loop -> mic.start() fresh
                        if fired:
                            break
                except Exception as e:
                    # A3: mic hardware errors (device unplugged, driver
                    # reset) or a transient model.predict() failure used
                    # to propagate out of listen_loop entirely - silently
                    # ending wake-word detection for the rest of the
                    # process (background thread) or crashing the app
                    # outright (main thread via run_listen()). Log, drop
                    # this iteration, and keep listening instead.
                    if self._stop_event.is_set():
                        break
                    logger.warning("Wake-word frame loop failed, restarting mic stream: %s", e)
                    try:
                        mic.stop()
                    except Exception:
                        from core.error_trace import log_swallowed as _lsw

                        _lsw("voice.wakeword.detector.listen_loop")
                    continue
                if not fired:
                    # Inner for loop only ends without firing when
                    # _stop_event was set (mic.frames() is otherwise
                    # infinite) - time to exit the outer loop too.
                    break
        finally:
            mic.stop()

    def listen(self, on_detected: Callable[[str], None]):
        self._stop_event.clear()
        self._thread = threading.Thread(target=self.listen_loop, args=(on_detected,), daemon=True)
        self._thread.start()

    def stop(self):
        self._stop_event.set()


_detector_instance: Optional[OpenWakeWordDetector] = None


def get_openwakeword_detector() -> OpenWakeWordDetector:
    global _detector_instance
    if _detector_instance is None:
        _detector_instance = OpenWakeWordDetector()
    return _detector_instance
