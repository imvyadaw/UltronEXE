"""
Audio processor
================
Small, dependency-light audio-format helpers shared by the newer Phase 9
engines - voice/wakeword/detector.py (openWakeWord wants 16kHz mono int16
frames), voice/stt/vosk_stt.py and voice/stt/whisper_stt.py (both want raw
PCM bytes/float arrays rather than an sr.AudioData object), and
voice/microphone/stream.py (raw mic capture).

This does NOT duplicate voice/noise_cancellation.py's spectral-subtraction
denoiser - that stays a separate, opt-in post-process step. This module is
just format plumbing: sr.AudioData <-> numpy <-> raw bytes, plus a linear
resampler for when a source and a model disagree on sample rate (e.g. a
48kHz mic feeding a 16kHz wake word model).
"""

try:
    import numpy as np

    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False

TARGET_SAMPLE_RATE = 16000  # what openWakeWord, Vosk, and Whisper all expect


def audio_data_to_numpy(audio, sample_rate: int = TARGET_SAMPLE_RATE) -> "np.ndarray":
    """Convert an sr.AudioData clip (from voice/microphone/microphone.py)
    to a mono float32 [-1, 1] numpy array at `sample_rate`. Returns an
    empty array if numpy isn't installed or audio is None."""
    if not HAS_NUMPY or audio is None:
        return np.array([], dtype="float32") if HAS_NUMPY else []
    raw = audio.get_raw_data(convert_rate=sample_rate, convert_width=2)
    return pcm16_bytes_to_float(raw)


def pcm16_bytes_to_float(raw: bytes) -> "np.ndarray":
    """Raw 16-bit PCM bytes -> mono float32 [-1, 1] numpy array."""
    if not HAS_NUMPY:
        return []
    return np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0


def float_to_pcm16_bytes(samples: "np.ndarray") -> bytes:
    """Mono float32 [-1, 1] numpy array -> raw 16-bit PCM bytes."""
    if not HAS_NUMPY:
        return b""
    clipped = np.clip(samples, -1.0, 1.0)
    return (clipped * 32767.0).astype(np.int16).tobytes()


def numpy_to_audio_data(samples: "np.ndarray", sample_rate: int = TARGET_SAMPLE_RATE):
    """Mono float32 numpy array -> sr.AudioData, for feeding back into
    stt_engine.py's transcribe_audio(), which takes AudioData objects."""
    import speech_recognition as sr

    return sr.AudioData(float_to_pcm16_bytes(samples), sample_rate, 2)


def resample_pcm16(raw: bytes, from_rate: int, to_rate: int) -> bytes:
    """Resample raw 16-bit mono PCM bytes from `from_rate` to `to_rate`
    using simple linear interpolation. Not audiophile-grade, but more
    than good enough for speech recognition / keyword spotting input,
    and needs no extra dependency (no scipy/soundfile/librosa)."""
    if from_rate == to_rate or not HAS_NUMPY:
        return raw
    samples = np.frombuffer(raw, dtype=np.int16).astype(np.float32)
    if len(samples) == 0:
        return raw
    duration = len(samples) / float(from_rate)
    new_len = max(1, int(round(duration * to_rate)))
    old_idx = np.linspace(0, len(samples) - 1, num=len(samples))
    new_idx = np.linspace(0, len(samples) - 1, num=new_len)
    resampled = np.interp(new_idx, old_idx, samples)
    return resampled.astype(np.int16).tobytes()


def rms(samples) -> float:
    """Root-mean-square energy of a float or int16 sample array/bytes -
    used as a cheap voice-activity / silence proxy."""
    if not HAS_NUMPY:
        return 0.0
    if isinstance(samples, bytes):
        samples = np.frombuffer(samples, dtype=np.int16).astype(np.float32) / 32768.0
    if len(samples) == 0:
        return 0.0
    return float(np.sqrt(np.mean(np.square(samples))))


def is_silence(samples, threshold: float = 0.01) -> bool:
    """True if a frame's RMS energy is below `threshold` - a quick,
    model-free gate used by voice/microphone/stream.py to skip running
    the (comparatively expensive) wake word model on obvious silence."""
    return rms(samples) < threshold


def chunk_bytes(raw: bytes, frame_bytes: int):
    """Yield fixed-size byte chunks from `raw` (last partial chunk,
    if any, is zero-padded to frame_bytes) - used to reshape whatever
    block size PyAudio hands back into the exact frame size a streaming
    model (e.g. openWakeWord) expects."""
    for start in range(0, len(raw), frame_bytes):
        chunk = raw[start : start + frame_bytes]
        if len(chunk) < frame_bytes:
            chunk = chunk + b"\x00" * (frame_bytes - len(chunk))
        yield chunk
