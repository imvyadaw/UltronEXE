"""
Face recognition
=================
Face *identification* (whose face is it?) via the `face_recognition`
library (dlib's ResNet face-embedding model under the hood) - a step up
from vision/face/detection.py's Haar Cascade, which only finds bounding
boxes. Known people are enrolled from one or more reference photos; each
enrollment is reduced to a 128-d face embedding and persisted to a JSON
file under storage/, so enrolled identities survive a restart without
needing a real database.

    pip install face_recognition   # pulls in dlib - on Windows this often
                                    # needs CMake + a C++ build toolchain
                                    # installed first; see the project's
                                    # README for the per-OS install notes.

Recognition works by comparing a detected face's embedding against every
enrolled embedding and taking the closest match under a distance
threshold - unmatched faces come back labeled "unknown" rather than a
forced (and likely wrong) guess.
"""

import json
from pathlib import Path
from typing import Dict, List, Optional

try:
    import face_recognition
    import numpy as np

    HAS_FACE_RECOGNITION = True
except ImportError:
    HAS_FACE_RECOGNITION = False

from vision.screen.capture import ScreenCapture
from config import STORAGE_DIR

ENCODINGS_FILE = Path(STORAGE_DIR) / "faces" / "known_faces.json"

# Lower = stricter match. face_recognition's own docs suggest ~0.6 as a
# reasonable default trade-off between false accepts and false rejects.
DEFAULT_TOLERANCE = 0.6


class FaceRecognition:
    """Enroll known people from reference photos, then identify faces in
    a new image against that enrolled set."""

    def __init__(self):
        self._screen = ScreenCapture()
        self._known: Dict[str, List[List[float]]] = {}
        self._loaded = False

    def _load(self) -> None:
        if self._loaded:
            return
        self._loaded = True
        if ENCODINGS_FILE.exists():
            try:
                self._known = json.loads(ENCODINGS_FILE.read_text(encoding="utf-8"))
            except Exception:
                self._known = {}

    def _save(self) -> Dict:
        try:
            ENCODINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
            ENCODINGS_FILE.write_text(json.dumps(self._known), encoding="utf-8")
            return {"ok": True}
        except Exception as e:
            return {"error": str(e)}

    def enroll(self, name: str, image=None, file_path: Optional[str] = None) -> Dict:
        """Add a reference face for `name`, from a PIL Image, an image
        file path, or the current screen if neither is given. Can be
        called multiple times per person (e.g. different angles/lighting)
        - all encodings for a name are checked on recognition."""
        if not HAS_FACE_RECOGNITION:
            return {
                "error": "face_recognition not installed - run: pip install face_recognition "
                "(see this module's docstring for the dlib build prerequisites)"
            }
        self._load()

        image = self._resolve_image(image, file_path)
        if isinstance(image, dict):
            return image

        try:
            rgb = np.array(image.convert("RGB"))
            encodings = face_recognition.face_encodings(rgb)
            if not encodings:
                return {
                    "error": "No face found in the given image - enrollment needs exactly "
                    "one clear, front-facing face per photo"
                }
            self._known.setdefault(name, []).append(encodings[0].tolist())
            save_result = self._save()
            if "error" in save_result:
                return save_result
            return {"success": True, "name": name, "reference_count": len(self._known[name])}
        except Exception as e:
            return {"error": str(e)}

    def forget(self, name: str) -> Dict:
        """Remove all enrolled references for `name`."""
        self._load()
        if name not in self._known:
            return {"error": f"'{name}' is not enrolled"}
        del self._known[name]
        return self._save()

    def list_known(self) -> Dict:
        self._load()
        return {"people": [{"name": n, "reference_count": len(e)} for n, e in self._known.items()]}

    def recognize(self, image=None, file_path: Optional[str] = None, tolerance: float = DEFAULT_TOLERANCE) -> Dict:
        """Identify every face in a PIL Image, an image file path, or the
        current screen if neither is given, against the enrolled set."""
        if not HAS_FACE_RECOGNITION:
            return {
                "error": "face_recognition not installed - run: pip install face_recognition "
                "(see this module's docstring for the dlib build prerequisites)"
            }
        self._load()

        image = self._resolve_image(image, file_path)
        if isinstance(image, dict):
            return image

        try:
            rgb = np.array(image.convert("RGB"))
            locations = face_recognition.face_locations(rgb)
            encodings = face_recognition.face_encodings(rgb, locations)

            results = []
            for (top, right, bottom, left), encoding in zip(locations, encodings):
                name, distance = self._best_match(encoding, tolerance)
                results.append(
                    {
                        "name": name,
                        "distance": round(distance, 4) if distance is not None else None,
                        "box": {"x": left, "y": top, "width": right - left, "height": bottom - top},
                    }
                )
            return {"face_count": len(results), "faces": results}
        except Exception as e:
            return {"error": str(e)}

    def _best_match(self, encoding, tolerance: float):
        best_name, best_distance = "unknown", None
        for name, refs in self._known.items():
            distances = face_recognition.face_distance(np.array(refs), encoding)
            if len(distances) == 0:
                continue
            min_distance = float(distances.min())
            if min_distance <= tolerance and (best_distance is None or min_distance < best_distance):
                best_name, best_distance = name, min_distance
        return best_name, best_distance

    def _resolve_image(self, image, file_path: Optional[str]):
        if file_path:
            try:
                from PIL import Image

                return Image.open(file_path)
            except Exception as e:
                return {"error": str(e)}
        if image is None:
            image = self._screen.capture()
        return image


_instance: "FaceRecognition" = None


def get_face_recognition() -> FaceRecognition:
    global _instance
    if _instance is None:
        _instance = FaceRecognition()
    return _instance
