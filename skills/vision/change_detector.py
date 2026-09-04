"""
skills/vision/change_detector.py
==================================
Camera-facing "did anything change since I last looked" engine - built
on the same camera_manager.py capture_snapshot() every other skill/vision
module uses (no second capture path), plus vision_memory.py for
persisting the baseline + event history across calls/restarts.

Sequence:
  1. set_baseline() - capture a frame now, remember it as "the reference".
  2. check()        - capture a new frame, diff it against the baseline
                       (grayscale + blur + threshold, same technique
                       object_detector.py/ocr_engine.py's docstrings
                       point at for "thin adapter, no duplicated model
                       logic" - here there's no existing diff module to
                       adapt, so this is the one place that owns it),
                       and report whether the changed-pixel percentage
                       clears CHANGE_DETECTION_THRESHOLD_PERCENT.
                       A detected change is recorded to vision_memory.py
                       and the new frame becomes the baseline for the
                       *next* check() - each call answers "what changed
                       since the last check", not "since the very first
                       one".

No description/object-detection/OCR logic here - if a caller wants to
know *what* changed, not just *that* something did, pair this with
camera_analyze_scene (scene_analyzer.py) on the returned snapshot_path.
"""

from typing import Optional

from config import CHANGE_DETECTION_THRESHOLD_PERCENT
from skills.vision.camera_manager import get_camera_manager
from skills.vision.vision_memory import get_vision_memory

try:
    import cv2

    _CV2_AVAILABLE = True
except Exception:
    _CV2_AVAILABLE = False


class ChangeDetector:
    """Baseline-vs-live-frame change detection - set_baseline() / check().
    Use get_change_detector()."""

    def __init__(self):
        self._camera = get_camera_manager()
        self._memory = get_vision_memory()

    def is_available(self) -> bool:
        return _CV2_AVAILABLE and self._camera.is_available()

    def status(self) -> dict:
        baseline = self._memory.get_baseline()
        return {
            "success": True,
            "camera_available": self._camera.is_available(),
            "baseline_set": baseline is not None,
            "baseline": baseline,
            "threshold_percent": CHANGE_DETECTION_THRESHOLD_PERCENT,
        }

    def set_baseline(self) -> dict:
        """Capture a frame right now and store it as the reference point
        for future check() calls."""
        if not _CV2_AVAILABLE:
            return {"success": False, "error": "opencv is not installed."}
        snapshot_path = self._camera.capture_snapshot()
        if snapshot_path is None:
            return {
                "success": False,
                "error": "Could not capture a camera frame - no webcam available or opencv not installed.",
            }
        baseline = self._memory.set_baseline(snapshot_path)
        return {"success": True, "baseline": baseline}

    def check(self, threshold_percent: Optional[float] = None) -> dict:
        """Capture a new frame and compare it against the stored
        baseline. Returns {"success": True, "changed": bool,
        "change_percent": float, "snapshot_path": str,
        "baseline_snapshot_path": str} - or {"success": False, "error"}
        if there's no baseline yet or the capture/diff fails. The new
        frame becomes the baseline for the next call regardless of the
        result, whether or not a change was detected."""
        if not _CV2_AVAILABLE:
            return {"success": False, "error": "opencv is not installed."}

        baseline = self._memory.get_baseline()
        if baseline is None:
            return {
                "success": False,
                "error": "No baseline set yet - call set_baseline() (or the camera_set_change_baseline "
                "tool) first, then check() to see what's changed since.",
            }

        new_path = self._camera.capture_snapshot()
        if new_path is None:
            return {
                "success": False,
                "error": "Could not capture a camera frame - no webcam available or opencv not installed.",
            }

        threshold = CHANGE_DETECTION_THRESHOLD_PERCENT if threshold_percent is None else threshold_percent
        change_percent = self._diff_percent(baseline["snapshot_path"], new_path)
        if change_percent is None:
            return {
                "success": False,
                "error": "Could not read one of the frames to compare (baseline file may be missing).",
                "snapshot_path": new_path,
            }

        changed = change_percent >= threshold
        result = {
            "success": True,
            "changed": changed,
            "change_percent": round(change_percent, 2),
            "threshold_percent": threshold,
            "snapshot_path": new_path,
            "baseline_snapshot_path": baseline["snapshot_path"],
        }

        if changed:
            self._memory.record_event(dict(result))

        # Rolling baseline: each check compares against what the camera
        # saw at the *previous* check, not the very first frame forever.
        self._memory.set_baseline(new_path)
        return result

    def history(self, limit: int = 10) -> dict:
        return {"success": True, "events": self._memory.get_recent_events(limit=limit)}

    def clear(self) -> dict:
        """Forget the current baseline and event history entirely."""
        self._memory.clear_baseline()
        self._memory.clear_events()
        return {"success": True}

    # -- internals ---------------------------------------------------------
    def _diff_percent(self, old_path: str, new_path: str) -> Optional[float]:
        old_img = cv2.imread(old_path)
        new_img = cv2.imread(new_path)
        if old_img is None or new_img is None:
            return None

        if old_img.shape != new_img.shape:
            new_img = cv2.resize(new_img, (old_img.shape[1], old_img.shape[0]))

        old_gray = cv2.GaussianBlur(cv2.cvtColor(old_img, cv2.COLOR_BGR2GRAY), (5, 5), 0)
        new_gray = cv2.GaussianBlur(cv2.cvtColor(new_img, cv2.COLOR_BGR2GRAY), (5, 5), 0)

        diff = cv2.absdiff(old_gray, new_gray)
        _, thresh = cv2.threshold(diff, 25, 255, cv2.THRESH_BINARY)

        changed_pixels = cv2.countNonZero(thresh)
        total_pixels = thresh.shape[0] * thresh.shape[1]
        if total_pixels == 0:
            return 0.0
        return (changed_pixels / total_pixels) * 100.0


_detector: Optional[ChangeDetector] = None


def get_change_detector() -> ChangeDetector:
    """Process-wide ChangeDetector singleton, matching this codebase's
    get_x() convention."""
    global _detector
    if _detector is None:
        _detector = ChangeDetector()
    return _detector
