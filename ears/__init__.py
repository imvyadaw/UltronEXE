"""
EARS (Phase 18.4)
==================
The audio-in counterpart to EYES/: five narrow modules instead of one
"listener.py", same one-module-per-concern shape used everywhere else
in this project.

    always_listen.py - the one module allowed to open a microphone
                        stream. Everything else in this package takes
                        audio (raw samples or already-transcribed
                        text) as an argument, same separation
                        live_camera.py draws for video.
    noise_filter.py   - cleans a raw audio chunk before anything else
                        touches it (spectral gating if `noisereduce`
                        is installed, a plain high-pass filter via
                        numpy if not, unchanged audio if even numpy
                        isn't there). Callers that want clean input
                        should filter first, transcribe second.
    multi_voice.py    - in-session speaker separation via a cheap
                        pitch/MFCC-summary fingerprint, same
                        aHash-not-a-real-embedding trade-off
                        EYES/face_scanner.py makes for faces. No
                        persistent naming table is added here (that
                        would duplicate MEMORY/face_memory.py's job
                        for a different modality) - it answers
                        "same speaker as before in this session?",
                        not "who is this".
    hindi_english.py  - text-level language identification
                        (Hindi/English/mixed) over an already-
                        transcribed utterance, so MOUTH/ can answer in
                        the language the user is actually using -
                        matches short_term.py's own bilingual
                        REFERENCE_WORDS set (yeh/woh/yahan/wahan)
                        already anticipating Hindi-English code-
                        switching.
    emotion_hear.py   - vocal-emotion reading, an honest stub the same
                        way EYES/emotion_read.py is: defines the
                        interface, best-effort delegates to an
                        optional third-party model, returns None with
                        no model installed rather than guessing from a
                        hand-rolled pitch rule.

Same contract as EYES/: every optional dependency is checked once at
import time, every public method degrades to None/[]/False/unchanged
input rather than raising, and cross-package imports stay lazy inside
methods.

Purely additive.
"""

from ears.always_listen import get_always_listen
from ears.noise_filter import get_noise_filter
from ears.multi_voice import get_multi_voice
from ears.hindi_english import get_hindi_english
from ears.emotion_hear import get_emotion_hearer

__all__ = [
    "get_always_listen",
    "get_noise_filter",
    "get_multi_voice",
    "get_hindi_english",
    "get_emotion_hearer",
]
