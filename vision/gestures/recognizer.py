"""
Gesture recognition
====================
Hand landmark detection + simple finger-counting gesture classification,
via MediaPipe's HandLandmarker task. The landmarker model
(hand_landmarker.task, ~8MB) isn't bundled - it's downloaded once from
Google's official MediaPipe model store on first use and cached under
storage/cache/models/, the same "don't bundle multi-megabyte weights,
fetch on demand" approach models/ollama/loader.py takes for LLMs.
"""

from pathlib import Path
from typing import Dict, List

try:
    import mediapipe as mp
    from mediapipe.tasks import python as mp_python
    from mediapipe.tasks.python import vision as mp_vision
    import numpy as np

    HAS_MEDIAPIPE = True
except ImportError:
    HAS_MEDIAPIPE = False

from vision.screen.capture import ScreenCapture
from config import CACHE_DIR

MODEL_URL = (
    "https://storage.googleapis.com/mediapipe-models/hand_landmarker/"
    "hand_landmarker/float16/latest/hand_landmarker.task"
)
MODEL_PATH = Path(CACHE_DIR) / "models" / "hand_landmarker.task"

# Landmark indices for each fingertip and the knuckle two joints below it,
# per MediaPipe's 21-point hand model - used to decide "is this finger up?"
FINGER_TIPS = {"thumb": 4, "index": 8, "middle": 12, "ring": 16, "pinky": 20}
FINGER_PIPS = {"thumb": 3, "index": 6, "middle": 10, "ring": 14, "pinky": 18}


class GestureRecognizer:
    """Hand detection + landmarks, with a simple finger-count-based
    gesture label (fist / open_palm / peace / thumbs_up / pointing)."""

    def __init__(self):
        self._screen = ScreenCapture()
        self._landmarker = None

    def _ensure_model(self) -> Dict:
        if MODEL_PATH.exists():
            return {"ok": True}
        try:
            import requests

            MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
            resp = requests.get(MODEL_URL, timeout=30)
            resp.raise_for_status()
            MODEL_PATH.write_bytes(resp.content)
            return {"ok": True}
        except Exception as e:
            return {"error": f"Could not download hand_landmarker.task: {e}"}

    def _get_landmarker(self):
        if self._landmarker is None:
            options = mp_vision.HandLandmarkerOptions(
                base_options=mp_python.BaseOptions(model_asset_path=str(MODEL_PATH)),
                num_hands=2,
            )
            self._landmarker = mp_vision.HandLandmarker.create_from_options(options)
        return self._landmarker

    @staticmethod
    def _classify(landmarks: List) -> str:
        """Very simple heuristic: count extended fingers via tip-vs-pip
        y-position (x-position for the thumb, since it extends sideways)."""
        up = 0
        for name, tip_idx in FINGER_TIPS.items():
            pip_idx = FINGER_PIPS[name]
            if name == "thumb":
                if abs(landmarks[tip_idx].x - landmarks[0].x) > abs(landmarks[pip_idx].x - landmarks[0].x):
                    up += 1
            else:
                if landmarks[tip_idx].y < landmarks[pip_idx].y:
                    up += 1

        if up == 0:
            return "fist"
        if up == 5:
            return "open_palm"
        if up == 1 and landmarks[FINGER_TIPS["index"]].y < landmarks[FINGER_PIPS["index"]].y:
            return "pointing"
        if up == 2:
            return "peace"
        return f"{up}_fingers"

    def detect(self, image=None) -> Dict:
        """Detect hands in a PIL Image, or the current screen if none given.
        Returns landmark counts + a best-effort gesture label per hand."""
        if not HAS_MEDIAPIPE:
            return {"error": "mediapipe not installed - run: pip install mediapipe"}

        model_status = self._ensure_model()
        if "error" in model_status:
            return model_status

        if image is None:
            image = self._screen.capture()
            if isinstance(image, dict):
                return image

        try:
            rgb = np.array(image.convert("RGB"))
            mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
            result = self._get_landmarker().detect(mp_image)

            hands = []
            for i, hand_landmarks in enumerate(result.hand_landmarks):
                handedness = result.handedness[i][0].category_name if result.handedness else "Unknown"
                hands.append(
                    {
                        "hand": handedness,
                        "gesture": self._classify(hand_landmarks),
                        "landmark_count": len(hand_landmarks),
                    }
                )
            return {"hand_count": len(hands), "hands": hands}
        except Exception as e:
            return {"error": str(e)}
