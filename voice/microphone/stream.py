"""
Microphone streaming
=====================
voice/microphone/microphone.py's Microphone.listen_once() is built around
SpeechRecognition's "wait for a phrase, then hand back one AudioData blob"
model - great for command transcription, wrong shape for a real-time
keyword spotter. openWakeWord (voice/wakeword/detector.py) needs a
continuous stream of small, fixed-size PCM frames (80ms @ 16kHz by
default) fed to it in a loop, so it can score every frame as it arrives.

This module opens the mic directly via PyAudio (bypassing
SpeechRecognition entirely) and exposes that as a simple frame generator.
It is intentionally independent of Microphone/get_microphone() - the two
can run at once conceptually, though in practice only one process holds
the mic at a time - so a caller can stream continuously for wake word
detection, then hand off to Microphone.listen_once() for the actual
command once the wake word fires.
"""

import queue
import threading
from typing import Generator, Optional

try:
    import pyaudio

    HAS_PYAUDIO = True
except ImportError:
    HAS_PYAUDIO = False

from config import WAKE_WORD_FRAME_MS
from voice.audio.processor import TARGET_SAMPLE_RATE, resample_pcm16
from core.logger import get_logger

logger = get_logger("mic_stream")

FORMAT_WIDTH_BYTES = 2  # 16-bit PCM


class MicrophoneStream:
    """Continuous raw-audio capture, yielding fixed-size 16kHz mono
    int16 PCM frames via a background PyAudio callback thread + queue -
    the callback itself does no work beyond enqueueing, so it can't
    stall real-time capture even if the consumer (the wake word model)
    is momentarily slow."""

    def __init__(
        self,
        sample_rate: int = TARGET_SAMPLE_RATE,
        frame_ms: int = WAKE_WORD_FRAME_MS,
        device_index: Optional[int] = None,
        capture_rate: Optional[int] = None,
    ):
        if not HAS_PYAUDIO:
            raise RuntimeError(
                "PyAudio not installed - run: pip install PyAudio "
                "(Windows: pip install pipwin && pipwin install pyaudio)"
            )
        self.sample_rate = sample_rate
        self.frame_size = int(sample_rate * frame_ms / 1000)
        self.frame_bytes = self.frame_size * FORMAT_WIDTH_BYTES
        self.device_index = device_index
        # Some mics/drivers don't support 16kHz capture directly - if the
        # caller didn't force a specific capture_rate, we auto-detect the
        # device's own native rate in start() (below) and resample down
        # from there, instead of blindly requesting 16kHz from hardware
        # that doesn't natively support it (silently degrades audio
        # quality on most laptop mics, which report 44100/48000Hz).
        self._capture_rate = capture_rate  # may be None until start()

        self._pa: Optional["pyaudio.PyAudio"] = None
        self._stream = None
        self._queue: "queue.Queue" = queue.Queue()
        self._running = threading.Event()
        self._leftover = b""

    def _callback(self, in_data, frame_count, time_info, status):
        if self._capture_rate != self.sample_rate:
            in_data = resample_pcm16(in_data, self._capture_rate, self.sample_rate)
        self._queue.put(in_data)
        return (None, pyaudio.paContinue)

    def start(self):
        if self._running.is_set():
            return
        self._pa = pyaudio.PyAudio()
        if self._capture_rate is None:
            # Auto-detect: ask PyAudio what this device's native rate
            # actually is, and capture at THAT rate, resampling down to
            # 16kHz ourselves (resample_pcm16) rather than asking the
            # device to natively produce 16kHz - many mics either refuse
            # that (raises here) or silently hand back distorted/aliased
            # audio, which is enough to tank wake word model accuracy
            # even when the phrase spoken is exactly right.
            try:
                if self.device_index is not None:
                    info = self._pa.get_device_info_by_index(self.device_index)
                else:
                    info = self._pa.get_default_input_device_info()
                self._capture_rate = int(info.get("defaultSampleRate", self.sample_rate))
            except Exception as e:
                logger.warning(
                    "Could not query native device sample rate (%s) - " "falling back to requesting %dHz directly.",
                    e,
                    self.sample_rate,
                )
                self._capture_rate = self.sample_rate
        capture_frame_size = int(self._capture_rate * (self.frame_size / self.sample_rate))
        self._stream = self._pa.open(
            format=pyaudio.paInt16,
            channels=1,
            rate=self._capture_rate,
            input=True,
            input_device_index=self.device_index,
            frames_per_buffer=max(1, capture_frame_size),
            stream_callback=self._callback,
        )
        self._running.set()
        self._stream.start_stream()
        logger.info(
            "Microphone stream started (capture=%dHz -> target=%dHz, frame=%dms).",
            self._capture_rate,
            self.sample_rate,
            int(1000 * self.frame_size / self.sample_rate),
        )

    def stop(self):
        self._running.clear()
        try:
            if self._stream is not None:
                self._stream.stop_stream()
                self._stream.close()
        except Exception:
            from core.error_trace import log_swallowed as _lsw

            _lsw("voice.microphone.stream.stop")
        try:
            if self._pa is not None:
                self._pa.terminate()
        except Exception:
            from core.error_trace import log_swallowed as _lsw

            _lsw("voice.microphone.stream.stop")
        self._stream = None
        self._pa = None
        # Drain so a restarted stream doesn't replay stale audio.
        while not self._queue.empty():
            try:
                self._queue.get_nowait()
            except queue.Empty:
                break
        self._leftover = b""

    def frames(self, timeout: float = 1.0) -> Generator[bytes, None, None]:
        """Yield exactly `self.frame_bytes`-sized raw PCM chunks
        indefinitely until stop() is called. Re-buffers PyAudio's
        arbitrarily-sized callback chunks into consistent frame_bytes
        pieces, since openWakeWord scores frame-by-frame."""
        if not self._running.is_set():
            self.start()
        buf = self._leftover
        while self._running.is_set():
            try:
                chunk = self._queue.get(timeout=timeout)
            except queue.Empty:
                continue
            buf += chunk
            while len(buf) >= self.frame_bytes:
                yield buf[: self.frame_bytes]
                buf = buf[self.frame_bytes :]
        self._leftover = buf

    @staticmethod
    def list_devices():
        """List available input device names/indices (PyAudio side) -
        for picking device_index=N when the default input isn't right."""
        if not HAS_PYAUDIO:
            return []
        pa = pyaudio.PyAudio()
        try:
            devices = []
            for i in range(pa.get_device_count()):
                info = pa.get_device_info_by_index(i)
                if info.get("maxInputChannels", 0) > 0:
                    devices.append((i, info.get("name"), int(info.get("defaultSampleRate", 16000))))
            return devices
        finally:
            pa.terminate()


_stream_instance: Optional[MicrophoneStream] = None


def get_microphone_stream() -> MicrophoneStream:
    global _stream_instance
    if _stream_instance is None:
        _stream_instance = MicrophoneStream()
    return _stream_instance
