"""
DISPLAY (Phase 18.3)
=====================
EYES/ produces data (boxes, embeddings, findings); nothing in EYES/
renders anything. DISPLAY/ is the read side that turns EYES/ output
(and MEMORY/'s naming of it) into something a screen or overlay can
show:

    screen_popup.py - a plain notification popup (tkinter if a display
                       is available; falls back to a log line if not,
                       same "headless box" case live_camera.py already
                       handles for the camera itself).
    face_label.py   - draws a name/box overlay on a frame, resolving
                       names through MEMORY/face_memory.py the same
                       way threat_sense.py's stranger check does.
    price_tag.py    - a small local (name -> price) lookup the user
                       teaches it, drawn as an overlay onto whichever
                       box object_finder.py hands it. Deliberately not
                       automatic - object_finder.py has no idea what a
                       blob *is*, so pairing a box with a price is
                       always a user action, never inferred.
    danger_alert.py - turns threat_sense.py findings into a spoken
                       line (through CORE.personality.speak(), the
                       same delivery reports.py already uses) plus an
                       optional popup.
    orb.py          - not a renderer itself (no game/graphics engine
                       here) - computes a small state dict (color,
                       pulse rate, label) from CORE.consciousness /
                       personality, for whatever UI layer eventually
                       draws the orb.

Every cross-module import (into EYES/, MEMORY/, or CORE/) is lazy,
matching the whole project's established pattern, so DISPLAY/ stays
importable even if a sibling package isn't wired up yet.

Purely additive - nothing outside this file imports from DISPLAY/.
"""

from display.screen_popup import get_screen_popup
from display.face_label import get_face_label
from display.price_tag import get_price_tag
from display.danger_alert import get_danger_alert
from display.orb import get_orb

__all__ = [
    "get_screen_popup",
    "get_face_label",
    "get_price_tag",
    "get_danger_alert",
    "get_orb",
]
