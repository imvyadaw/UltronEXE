"""
Wake word live diagnostic
==========================
Run this directly (not through main.py) to see EXACTLY what's happening
with your mic and the wake word model in real time, instead of guessing:

    python tools/wakeword_debug.py

It prints, ~12 times a second, a line like:

    mic level: [########------------]  42%   |  hey_ultron score: 0.71  <-- FIRE (>=0.30)

- "mic level" is your raw microphone volume (0-100%), independent of
  the wake word model entirely. This tells you if PyAudio is even
  capturing real audio from the right device.
    -> stays at 0% the whole time, even when you talk loudly right into
       the mic -> PyAudio has the WRONG input device, or the mic is
       muted/disabled at the OS level. This is a mic/driver problem,
       not a ULTRON problem.
    -> jumps up when you talk, normal range otherwise -> mic capture is
       fine, so the problem is specifically the wake word model/score.

- "score" is openWakeWord's smoothed confidence (same number used
  in the real assistant). Say "Hey Ultron" a few times and watch it:
    -> stays near 0.00-0.05 the whole time, never rises even a little
       when you say it -> the model itself likely failed to load
       properly (see the "openWakeWord loaded..." line printed at
       startup below - check models_downloaded_ok).
    -> rises noticeably (e.g. to 0.15-0.25) when you say it but doesn't
       quite cross the current threshold -> just needs the threshold/
       gain nudged down further (this script prints the exact numbers
       so we know precisely how far off it is, instead of guessing).
    -> crosses threshold and "<-- FIRE" appears -> working correctly.

Ctrl+C to stop. Share the printed startup line + a few sample "score"
values from when you say the wake word - that tells us exactly which
of the two problems (mic capture vs. model scoring) it is.
"""

import sys
import numpy as np

sys.path.insert(0, ".")

from config import (
    WAKE_WORD_THRESHOLD,
    WAKE_WORD_MIC_GAIN,
    WAKE_WORD_SMOOTH_FRAMES,
    WAKE_WORD_FRAME_MS,
)
from voice.microphone.stream import MicrophoneStream


def main():
    print(
        f"Config: threshold={WAKE_WORD_THRESHOLD}  gain={WAKE_WORD_MIC_GAIN}x  "
        f"smoothing={WAKE_WORD_SMOOTH_FRAMES} frames\n"
    )

    try:
        import openwakeword
        from openwakeword.model import Model as OWWModel
    except ImportError:
        print("openwakeword not installed - run: pip install openwakeword")
        return

    print("Available mic input devices:")
    for idx, name, rate in MicrophoneStream.list_devices():
        print(f"  [{idx}] {name}  (native rate: {rate}Hz)")
    print()

    download_ok = True
    try:
        openwakeword.utils.download_models()
    except Exception as e:
        download_ok = False
        print(f"!! Model download failed: {e}")
        print(
            "!! This is very likely your problem - reconnect to the "
            "internet and re-run this script to force a clean download.\n"
        )

    model = OWWModel(wakeword_models=["hey_ultron"], inference_framework="onnx")
    probe = model.predict(np.zeros(1280, dtype=np.int16))
    print(
        f"Startup self-test: models_downloaded_ok={download_ok}  "
        f"probe_result={probe if probe else 'EMPTY (bad sign)'}\n"
    )
    model.reset()

    from collections import deque

    window = deque(maxlen=max(1, WAKE_WORD_SMOOTH_FRAMES))

    mic = MicrophoneStream(frame_ms=WAKE_WORD_FRAME_MS)
    mic.start()
    print("Listening... say 'Hey Ultron' a few times. Ctrl+C to stop.\n")

    try:
        for frame_bytes in mic.frames():
            frame = np.frombuffer(frame_bytes, dtype=np.int16)

            # Raw mic level, BEFORE gain - tells us if capture itself works.
            rms = float(np.sqrt(np.mean(frame.astype(np.float32) ** 2))) if len(frame) else 0.0
            level_pct = min(100, int((rms / 3000.0) * 100))  # rough scale for display only
            bar = "#" * (level_pct // 5) + "-" * (20 - level_pct // 5)

            if WAKE_WORD_MIC_GAIN != 1.0:
                boosted = frame.astype(np.float32) * WAKE_WORD_MIC_GAIN
                frame = np.clip(boosted, -32768, 32767).astype(np.int16)

            predictions = model.predict(frame)
            raw_score = predictions.get("hey_ultron", 0.0)
            window.append(raw_score)
            score = sum(window) / len(window)
            fire = " <-- FIRE" if score >= WAKE_WORD_THRESHOLD else ""

            print(
                f"\rmic level: [{bar}] {level_pct:3d}%   |   " f"hey_ultron score: {score:.3f}{fire}   ",
                end="",
                flush=True,
            )

            if fire:
                print()  # newline so FIRE lines don't overwrite each other
                model.reset()
                window.clear()

    except KeyboardInterrupt:
        print("\n\nStopped.")
    finally:
        mic.stop()


if __name__ == "__main__":
    main()
