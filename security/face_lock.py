"""
Face Lock (SECURITY)
=====================
Enrolls one or more reference faces and verifies a new snapshot
against them - the "is this actually Vishal" gate that
intruder_alert.py counts failures against and that privacy_shield.py
can require before it will drop privacy mode. Built on
`face_recognition` (dlib's ResNet embeddings under the hood), which
is the only backend here: no cloud face API, nothing leaves the
machine.

Encodings are 128-d vectors stored locally (pickle, gitignored by
convention) under SECURITY_FACE_DATA_DIR - never the source images
themselves, so a leaked data dir doesn't leak a photo of anyone. One
name can hold several encodings (different angles/lighting); a
verify() is a match if ANY stored encoding for ANY name is within
tolerance, and the closest one wins.

Same optional-dependency contract as the rest of this project: no
`face_recognition`, no enrolled faces, or any failure all collapse to
{"success": False, ...} rather than an exception. Vision/webcam
capture itself is out of scope - callers (this phase's
intruder_alert.py, or a future gesture/vision phase) hand this module
an image path or an in-memory array; it only ever does the
encode-and-compare.
"""

import os
import pickle
from typing import Dict, List, Optional

try:
    import face_recognition
    import numpy as np

    _FACE_RECOGNITION_AVAILABLE = True
except Exception:
    _FACE_RECOGNITION_AVAILABLE = False

FACE_DATA_DIR_ENV = "SECURITY_FACE_DATA_DIR"
DEFAULT_FACE_DATA_DIR = "data/security/faces"
ENCODINGS_FILENAME = "encodings.pkl"
DEFAULT_TOLERANCE = 0.6  # face_recognition's own default; lower = stricter


class FaceLock:
    """Local face enrollment/verification. Use get_face_lock()."""

    def __init__(self):
        self._encodings: Dict[str, List] = {}
        self._loaded = False

    def is_available(self) -> bool:
        return _FACE_RECOGNITION_AVAILABLE

    def _data_dir(self) -> str:
        path = os.environ.get(FACE_DATA_DIR_ENV, DEFAULT_FACE_DATA_DIR)
        os.makedirs(path, exist_ok=True)
        return path

    def _store_path(self) -> str:
        return os.path.join(self._data_dir(), ENCODINGS_FILENAME)

    def _load(self) -> None:
        if self._loaded:
            return
        self._loaded = True
        path = self._store_path()
        if os.path.exists(path):
            try:
                with open(path, "rb") as fh:
                    self._encodings = pickle.load(fh)
            except Exception:
                self._encodings = {}

    def _save(self) -> None:
        try:
            with open(self._store_path(), "wb") as fh:
                pickle.dump(self._encodings, fh)
        except Exception:
            from core.error_trace import log_swallowed as _lsw

            _lsw("security.face_lock._save")

    def enroll(self, name: str, image_path: str) -> Dict:
        """Extracts the (first) face in `image_path` and adds its
        encoding under `name`, on top of any it already has. Returns
        {"success": bool, "encodings_for_name": int, "error": Optional[str]}."""
        if not self.is_available():
            return {"success": False, "encodings_for_name": 0, "error": "face_recognition not available"}
        if not name or not image_path:
            return {"success": False, "encodings_for_name": 0, "error": "name and image_path both required"}
        self._load()
        try:
            image = face_recognition.load_image_file(image_path)
            found = face_recognition.face_encodings(image)
            if not found:
                return {
                    "success": False,
                    "encodings_for_name": len(self._encodings.get(name, [])),
                    "error": "no face detected in image",
                }
            self._encodings.setdefault(name, []).append(found[0])
            self._save()
            return {"success": True, "encodings_for_name": len(self._encodings[name]), "error": None}
        except Exception as exc:
            return {"success": False, "encodings_for_name": 0, "error": str(exc)}

    def verify(self, image_path: str, tolerance: float = DEFAULT_TOLERANCE) -> Dict:
        """Checks the (first) face in `image_path` against every
        enrolled name. Returns {"success": bool, "match": Optional[str],
        "confidence": float, "error": Optional[str]}. "success" means
        a match was found within `tolerance`; "confidence" is
        1 - distance for the closest candidate (0 if none)."""
        if not self.is_available():
            return {"success": False, "match": None, "confidence": 0.0, "error": "face_recognition not available"}
        self._load()
        if not self._encodings:
            return {"success": False, "match": None, "confidence": 0.0, "error": "no faces enrolled"}
        try:
            image = face_recognition.load_image_file(image_path)
            found = face_recognition.face_encodings(image)
            if not found:
                return {"success": False, "match": None, "confidence": 0.0, "error": "no face detected in image"}
            probe = found[0]

            best_name, best_distance = None, None
            for name, encodings in self._encodings.items():
                distances = face_recognition.face_distance(encodings, probe)
                local_best = float(np.min(distances))
                if best_distance is None or local_best < best_distance:
                    best_name, best_distance = name, local_best

            confidence = max(0.0, 1.0 - best_distance)
            if best_distance <= tolerance:
                return {"success": True, "match": best_name, "confidence": confidence, "error": None}
            return {"success": False, "match": None, "confidence": confidence, "error": "no match within tolerance"}
        except Exception as exc:
            return {"success": False, "match": None, "confidence": 0.0, "error": str(exc)}

    def forget(self, name: str) -> Dict:
        """Removes all encodings for `name`. Returns
        {"success": bool, "error": Optional[str]}."""
        self._load()
        if name not in self._encodings:
            return {"success": False, "error": f"'{name}' not enrolled"}
        del self._encodings[name]
        self._save()
        return {"success": True, "error": None}

    def enrolled_names(self) -> List[str]:
        """Returns the list of currently enrolled names."""
        self._load()
        return list(self._encodings.keys())


_face_lock: Optional[FaceLock] = None


def get_face_lock() -> FaceLock:
    global _face_lock
    if _face_lock is None:
        _face_lock = FaceLock()
    return _face_lock
