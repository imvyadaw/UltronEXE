"""
Anomaly detector
===================
Flags likely error dialogs, crashes, or unexpected popups on screen,
combining two cheap signals rather than a trained anomaly model (no
such model is bundled, same stance as every other vision/ module here):

  1. OCR keyword scan (via omni_parser.py's text elements) for common
     error/crash vocabulary ("error", "exception", "not responding",
     "access denied", "stopped working", ...).
  2. Frame-to-frame screen diffing: keep a hash of the last-seen screen
     region-by-region (coarse grid, not pixel-perfect) and flag a
     sudden, large, localized change as "something new appeared" - a
     useful signal even when the new thing has no matching keyword
     (e.g. a modal in a language the OCR model doesn't cover well).

Meant to be polled periodically (e.g. every few seconds from a
background watcher) rather than called once - check() is cheap enough
for that (one screenshot + OCR + a numpy diff), but still real work, so
this module does not start its own thread; the caller decides the cadence.
"""

import hashlib
from typing import Dict, List, Optional

try:
    import numpy as np

    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False

from computer_vision.omni_parser import get_omni_parser
from vision.screen.capture import ScreenCapture
from core.logger import get_logger

logger = get_logger("ultron.interaction.anomaly")

ERROR_KEYWORDS = {
    "error",
    "exception",
    "crash",
    "crashed",
    "failed",
    "failure",
    "not responding",
    "stopped working",
    "access denied",
    "permission denied",
    "fatal",
    "unhandled",
    "traceback",
    "warning",
    "critical",
    "unresponsive",
}

GRID_SIZE = 8  # coarse width x height cells for the diff hash
DIFF_THRESHOLD = 0.35  # fraction of grid cells that must change to flag "large change"


def _grid_hash(image) -> List[str]:
    """Coarse per-cell average-color hash - cheap and robust to minor
    rendering noise (cursor blink, clock ticking) while still catching a
    real dialog/popup appearing."""
    arr = np.array(image.convert("RGB").resize((GRID_SIZE * 8, GRID_SIZE * 8)))
    h, w, _ = arr.shape
    ch, cw = h // GRID_SIZE, w // GRID_SIZE
    cells = []
    for gy in range(GRID_SIZE):
        for gx in range(GRID_SIZE):
            cell = arr[gy * ch : (gy + 1) * ch, gx * cw : (gx + 1) * cw]
            avg = cell.reshape(-1, 3).mean(axis=0).astype(int)
            cells.append(hashlib.md5(avg.tobytes()).hexdigest()[:8])
    return cells


class AnomalyDetector:
    """Holds the previous grid hash between check() calls, so it's a
    per-session/per-watcher instance, not a stateless function - two
    independent watchers polling different monitors would want their own."""

    def __init__(self):
        self._screen = ScreenCapture()
        self._parser = get_omni_parser()
        self._prev_grid: Optional[List[str]] = None

    def check(self) -> Dict:
        image = self._screen.capture()
        if isinstance(image, dict):
            return image

        findings = {"keyword_hits": [], "large_change": False, "changed_cell_ratio": 0.0}

        parse = self._parser.parse(image=image)
        if isinstance(parse, dict) and "elements" in parse:
            for el in parse["elements"]:
                text = (el.get("text") or "").lower()
                for kw in ERROR_KEYWORDS:
                    if kw in text:
                        findings["keyword_hits"].append({"keyword": kw, "text": el.get("text"), "box": el["box"]})

        if HAS_NUMPY:
            grid = _grid_hash(image)
            if self._prev_grid is not None:
                changed = sum(1 for a, b in zip(grid, self._prev_grid) if a != b)
                ratio = changed / len(grid)
                findings["changed_cell_ratio"] = round(ratio, 3)
                findings["large_change"] = ratio >= DIFF_THRESHOLD
            self._prev_grid = grid

        is_anomaly = bool(findings["keyword_hits"]) or findings["large_change"]
        findings["is_anomaly"] = is_anomaly
        if is_anomaly:
            logger.info(
                f"Screen anomaly detected: {len(findings['keyword_hits'])} keyword hits, "
                f"changed_cell_ratio={findings['changed_cell_ratio']}"
            )
        return findings

    def reset_baseline(self) -> None:
        self._prev_grid = None


_detector: Optional[AnomalyDetector] = None


def get_anomaly_detector() -> AnomalyDetector:
    global _detector
    if _detector is None:
        _detector = AnomalyDetector()
    return _detector
