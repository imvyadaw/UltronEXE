"""
Night Eye
=========
Two small, cheap operations: decide whether a frame is dark enough
that the rest of EYES/ (face_scanner, object_finder, threat_sense) is
about to get worse input than usual, and optionally brighten it before
handing it onward. Brightness is judged by mean grayscale pixel value
against LOW_LIGHT_THRESHOLD - a plain heuristic, not a learned
exposure model, matching this whole package's stance on avoiding fake
precision it can't back up.

Enhancement is CLAHE (contrast-limited adaptive histogram equalization)
applied to the luminance channel only, not a flat brightness push - it
avoids blowing out the parts of the frame that are already lit
(a lamp in an otherwise dark room), which a naive gamma boost on the
whole frame would wash out.
"""

from typing import Optional

try:
    import cv2

    _CV2_AVAILABLE = True
except Exception:
    _CV2_AVAILABLE = False

LOW_LIGHT_THRESHOLD = 60  # mean grayscale value (0-255) below which a frame counts as "low light"


class NightEye:
    """Low-light detection + CLAHE enhancement. Use get_night_eye()."""

    def is_available(self) -> bool:
        return _CV2_AVAILABLE

    def is_low_light(self, frame) -> Optional[bool]:
        """None (not False) when there's no way to tell - missing
        frame or backend unavailable - so callers don't mistake
        "couldn't check" for "confirmed well-lit"."""
        if not self.is_available() or frame is None:
            return None
        try:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            return bool(gray.mean() < LOW_LIGHT_THRESHOLD)
        except Exception:
            return None

    def enhance(self, frame):
        """Returns a brightened copy of frame, or the original frame
        unchanged if enhancement isn't possible (rather than None -
        callers that just want "the best frame available" shouldn't
        have to special-case a failed enhancement)."""
        if not self.is_available() or frame is None:
            return frame
        try:
            lab = cv2.cvtColor(frame, cv2.COLOR_BGR2LAB)
            l_channel, a_channel, b_channel = cv2.split(lab)
            clahe = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(8, 8))
            l_enhanced = clahe.apply(l_channel)
            merged = cv2.merge((l_enhanced, a_channel, b_channel))
            return cv2.cvtColor(merged, cv2.COLOR_LAB2BGR)
        except Exception:
            return frame


_night_eye: Optional[NightEye] = None


def get_night_eye() -> NightEye:
    global _night_eye
    if _night_eye is None:
        _night_eye = NightEye()
    return _night_eye
