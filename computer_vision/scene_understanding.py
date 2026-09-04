"""
Scene understanding (continuous)
===================================
vision/scene_understanding.py's SceneUnderstanding.describe_screen() is a
single-shot "what's on screen right now" snapshot. This module wraps it
(does not replace it - same rule as every file in this phase) to add
what a continuous companion actually needs: "what changed since I last
looked" - a running diff between the current describe_screen() call and
the previous one, phrased as a short list of plain-English deltas rather
than two full snapshots the caller has to diff themselves.

Complements anomaly_detector.py rather than overlapping it: anomaly
detection is about *alarming* changes (errors, crashes, popups) worth
interrupting the user for; this module is about *narrating* ordinary
changes (new window text, a region's content changed) for things like a
"what's changed on my screen" voice query or a running activity log -
lower urgency, broader scope.
"""

from typing import Dict, List, Optional

from vision.scene_understanding import get_scene_understanding
from core.logger import get_logger

logger = get_logger("ultron.interaction.scene_understanding")


def _text_set(snapshot: Dict) -> set:
    """describe_screen() buckets OCR text under "text_by_layout_region"
    (region-name -> list of strings), not a flat list of {"text": ...}
    dicts - flatten that structure into a plain set of strings for diffing."""
    layout = snapshot.get("text_by_layout_region", {})
    words = set()
    for texts in layout.values():
        words.update(texts)
    return words


class ContinuousSceneUnderstanding:
    """Holds the last snapshot so consecutive calls can be diffed - one
    instance per watcher/session, same reasoning as AnomalyDetector."""

    def __init__(self):
        self._base = get_scene_understanding()
        self._last_snapshot: Optional[Dict] = None

    def look(self, include_objects: bool = True) -> Dict:
        """One fresh snapshot via the Phase 16 describe_screen(), with no
        diffing - use this for a one-off "what's on my screen" query."""
        return self._base.describe_screen(include_objects=include_objects)

    def look_and_diff(self, include_objects: bool = True) -> Dict:
        """Snapshot the screen and report what's different from the last
        call to this method. First call has nothing to diff against, so
        it just establishes the baseline."""
        snapshot = self._base.describe_screen(include_objects=include_objects)
        if isinstance(snapshot, dict) and "error" in snapshot:
            return snapshot

        if self._last_snapshot is None:
            self._last_snapshot = snapshot
            return {"snapshot": snapshot, "changes": [], "is_first_look": True}

        changes: List[str] = []
        prev_text = _text_set(self._last_snapshot)
        curr_text = _text_set(snapshot)

        appeared = curr_text - prev_text
        disappeared = prev_text - curr_text
        if appeared:
            sample = ", ".join(list(appeared)[:5])
            changes.append(f"New text appeared: {sample}" + (" ..." if len(appeared) > 5 else ""))
        if disappeared:
            sample = ", ".join(list(disappeared)[:5])
            changes.append(f"Text disappeared: {sample}" + (" ..." if len(disappeared) > 5 else ""))

        prev_objects = {o.get("label") for o in (self._last_snapshot.get("objects") or []) if isinstance(o, dict)}
        curr_objects = {o.get("label") for o in (snapshot.get("objects") or []) if isinstance(o, dict)}
        new_objects = curr_objects - prev_objects
        if new_objects:
            changes.append(f"New objects detected: {', '.join(str(o) for o in new_objects)}")

        self._last_snapshot = snapshot
        return {"snapshot": snapshot, "changes": changes, "is_first_look": False, "has_changed": bool(changes)}

    def reset(self) -> None:
        self._last_snapshot = None


_watcher: Optional[ContinuousSceneUnderstanding] = None


def get_continuous_scene_understanding() -> ContinuousSceneUnderstanding:
    global _watcher
    if _watcher is None:
        _watcher = ContinuousSceneUnderstanding()
    return _watcher
