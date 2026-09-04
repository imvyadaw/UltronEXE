"""
Noise cancellation
====================
Audio preprocessing for voice/stt/ - spectral subtraction noise
reduction, implemented in plain numpy (STFT via manual framing + FFT,
overlap-add reconstruction) so it needs no extra dependency beyond what
Vision already requires. Estimates the noise floor from the first
`noise_sample_ms` of the clip (assumed to be near-silence/room tone -
true for the leading edge of most push-to-talk-style captures), then
subtracts that magnitude profile from every frame before reconstructing
the waveform.

This is a real, working denoiser - not a stub - but it is a classic
spectral-subtraction implementation, not a trained model: it helps with
steady background hums/fans/hiss and does little for other transient
noise (a dog bark, a door slam) or another person talking. Wired into
voice/microphone.py's listen_once() as an opt-in post-process step
(DENOISE_ENABLED below) - failures here always fall back to the raw,
un-denoised audio rather than breaking capture.
"""

try:
    import numpy as np

    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False

DENOISE_ENABLED = True  # flip off if it ever hurts transcription accuracy
# more than the noise it's removing, for your mic
FRAME_SIZE = 1024
HOP_SIZE = 256
NOISE_SAMPLE_MS = 300
OVER_SUBTRACTION = 1.8  # how aggressively to subtract the noise estimate
NOISE_FLOOR_RATIO = 0.05  # never subtract below this fraction of a frame's own energy


def _stft(samples: "np.ndarray", frame_size: int, hop: int):
    window = np.hanning(frame_size)
    n_frames = max(1, 1 + (len(samples) - frame_size) // hop)
    frames = np.zeros((n_frames, frame_size // 2 + 1), dtype=np.complex64)
    for i in range(n_frames):
        start = i * hop
        chunk = samples[start : start + frame_size]
        if len(chunk) < frame_size:
            chunk = np.pad(chunk, (0, frame_size - len(chunk)))
        frames[i] = np.fft.rfft(chunk * window)
    return frames


def _istft(frames: "np.ndarray", frame_size: int, hop: int, out_len: int):
    window = np.hanning(frame_size)
    output = np.zeros(out_len + frame_size, dtype=np.float32)
    weight = np.zeros(out_len + frame_size, dtype=np.float32)
    for i, frame in enumerate(frames):
        start = i * hop
        chunk = np.fft.irfft(frame, n=frame_size).astype(np.float32) * window
        output[start : start + frame_size] += chunk
        weight[start : start + frame_size] += window**2
    weight[weight < 1e-8] = 1.0
    return (output / weight)[:out_len]


def denoise_samples(samples: "np.ndarray", sample_rate: int) -> "np.ndarray":
    """Spectral-subtraction denoise on a float32 [-1, 1] mono sample
    array. Returns a same-length float32 array."""
    if len(samples) < FRAME_SIZE * 2:
        return samples  # too short to estimate a noise profile usefully

    # Pad on both sides so every real sample falls inside the region
    # where overlapping windows sum to a healthy, non-near-zero weight -
    # without this, the true start/end samples sit under partial window
    # coverage and dividing by that tiny weight in _istft blows up the
    # reconstructed amplitude right at the edges.
    pad = FRAME_SIZE
    padded = np.pad(samples, (pad, pad))

    spectrum = _stft(padded, FRAME_SIZE, HOP_SIZE)
    magnitude, phase = np.abs(spectrum), np.angle(spectrum)

    noise_frames = max(1, int((NOISE_SAMPLE_MS / 1000) * sample_rate / HOP_SIZE))
    noise_frames = min(noise_frames, magnitude.shape[0] - 1)
    noise_profile = magnitude[:noise_frames].mean(axis=0)

    floor = magnitude * NOISE_FLOOR_RATIO
    cleaned_magnitude = np.maximum(magnitude - noise_profile * OVER_SUBTRACTION, floor)

    cleaned_spectrum = cleaned_magnitude * np.exp(1j * phase)
    reconstructed = _istft(cleaned_spectrum, FRAME_SIZE, HOP_SIZE, len(padded))
    return reconstructed[pad : pad + len(samples)]


def denoise_audio_data(audio):
    """Denoise an sr.AudioData clip (as captured by voice/microphone.py)
    and return a new sr.AudioData with the same sample rate/width. Falls
    back to returning `audio` unchanged on any error - never raises, so
    a failure here never breaks the voice pipeline."""
    if not HAS_NUMPY:
        return audio
    try:
        import speech_recognition as sr

        sample_rate = audio.sample_rate
        raw = audio.get_raw_data(convert_rate=sample_rate, convert_width=2)
        samples = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0

        cleaned = denoise_samples(samples, sample_rate)
        cleaned = np.clip(cleaned, -1.0, 1.0)
        cleaned_int16 = (cleaned * 32768.0).astype(np.int16)

        return sr.AudioData(cleaned_int16.tobytes(), sample_rate, 2)
    except Exception:
        return audio
