"""
EYES (Phase 18.3)
==================
Where MEMORY/face_memory.py already owns the *naming* half of "who is
this" (embedding_id <-> name, best-effort via recognize_live()), this
package is the other half it deliberately deferred: producing frames
and reading something out of them. Six narrow modules instead of one
big "vision.py", matching the one-module-per-concern shape already
used by MEMORY/ and COMMAND/:

    live_camera.py   - frame source. Nothing else in this package
                        opens a camera; everything else takes a frame
                        as an argument.
    face_scanner.py  - face detection + a cheap perceptual-hash
                        "embedding" (no bundled ML model). This is the
                        concrete backend MEMORY/face_memory.py's
                        recognize_live() was written to call through
                        vision.face_recognition.get_embedding_id - see
                        that module's docstring for the compatibility
                        shim.
    object_finder.py - coarse blob/contour object localization, same
                        no-model constraint as face_scanner.
    text_reader.py   - OCR via pytesseract if installed; None if not.
    night_eye.py      - low-light detection + enhancement.
    threat_sense.py  - generic hazard heuristics (motion spikes,
                        fire/smoke color+brightness, unrecognized
                        person), not weapon or object-specific
                        classification - deliberately scoped down,
                        same reasoning MEMORY/place_memory.py gives
                        for staying exact-match instead of fuzzy: a
                        wrong guess here would be worse than no guess.
    emotion_read.py  - best-effort against an optional third-party
                        model; an honestly-marked stub (returns None)
                        when none is installed, same as
                        vision.face_recognition was in Phase 17.

Every module here is best-effort by construction: cv2/numpy/
pytesseract are all optional imports, checked once at import time via
each module's own `_available()` helper, and every public method
degrades to None/[]/False rather than raising when the optional
dependency or the camera itself isn't there. That's not a cop-out
specific to this package - it's the same contract face_memory.py
already promised its callers ("never a crash").

Purely additive - nothing in Phase 1-18.2 imports from here except the
one compatibility shim documented in face_scanner.py.
"""

from eyes.live_camera import get_live_camera
from eyes.face_scanner import get_face_scanner
from eyes.object_finder import get_object_finder
from eyes.text_reader import get_text_reader
from eyes.night_eye import get_night_eye
from eyes.threat_sense import get_threat_sense
from eyes.emotion_read import get_emotion_reader

__all__ = [
    "get_live_camera",
    "get_face_scanner",
    "get_object_finder",
    "get_text_reader",
    "get_night_eye",
    "get_threat_sense",
    "get_emotion_reader",
]
