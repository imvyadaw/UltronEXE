"""
Face Label
==========
Pairs EYES/face_scanner.py's boxes with MEMORY/face_memory.py's names
and draws the result onto a copy of the frame - a box plus "Alex" or
"unknown" above it. Doesn't touch face_memory's state (no learn_face()
call from here); this module only reads. Teaching a new name to a
face stays a deliberate MEMORY/face_memory.learn_face() call elsewhere,
not something drawing a label should trigger as a side effect.
"""

from typing import List, Optional

try:
    import cv2

    _CV2_AVAILABLE = True
except Exception:
    _CV2_AVAILABLE = False

BOX_COLOR = (80, 200, 120)  # BGR
UNKNOWN_COLOR = (60, 60, 220)  # BGR - unknown faces get a distinct color


class FaceLabel:
    """Draws name/box overlays for detected faces. Use get_face_label()."""

    def is_available(self) -> bool:
        return _CV2_AVAILABLE

    def annotate(self, frame):
        """Returns a copy of frame with a box + name (or "unknown")
        drawn over every detected face. Returns the original frame
        unchanged if drawing isn't possible - same "best available
        result, not a crash" contract as night_eye.enhance()."""
        if not self.is_available() or frame is None:
            return frame
        try:
            from eyes.face_scanner import get_face_scanner
            from memory.face_memory import get_face_memory

            scanner = get_face_scanner()
            face_memory = get_face_memory()
            boxes = scanner.detect_faces(frame)
            if not boxes:
                return frame

            annotated = frame.copy()
            for box in boxes:
                x, y, w, h = box
                embedding_id = scanner.embedding_id(frame, box=box)
                name = face_memory.recognize(embedding_id) if embedding_id else None
                label = name or "unknown"
                color = BOX_COLOR if name else UNKNOWN_COLOR
                cv2.rectangle(annotated, (x, y), (x + w, y + h), color, 2)
                cv2.putText(annotated, label, (x, max(y - 10, 15)), cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)
            return annotated
        except Exception:
            return frame

    def labels_for(self, frame) -> List[str]:
        """Convenience: just the resolved names/"unknown" strings for
        each detected face, no drawing - useful for a caller that
        wants text only (e.g. a report or a spoken summary)."""
        if frame is None:
            return []
        try:
            from eyes.face_scanner import get_face_scanner
            from memory.face_memory import get_face_memory

            scanner = get_face_scanner()
            face_memory = get_face_memory()
            boxes = scanner.detect_faces(frame)
            labels = []
            for box in boxes:
                embedding_id = scanner.embedding_id(frame, box=box)
                name = face_memory.recognize(embedding_id) if embedding_id else None
                labels.append(name or "unknown")
            return labels
        except Exception:
            return []


_face_label: Optional[FaceLabel] = None


def get_face_label() -> FaceLabel:
    global _face_label
    if _face_label is None:
        _face_label = FaceLabel()
    return _face_label
