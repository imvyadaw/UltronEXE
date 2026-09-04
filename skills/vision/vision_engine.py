"""
skills/vision/vision_engine.py
================================
Orchestrates camera_manager.py (capture) + vision_provider.py
("local_vision_provider" - Ollama+LLaVA) + remote_vision_provider.py
("remote_vision_provider" - Gemini) into the single calls
camera_skill.py and ai/vision_skill_tools.py actually expose: see() and
status(). No camera or model logic lives here - only the sequencing and
the combined result shape.

Local-first, remote-fallback, same chaining idea vision_provider.py's
docstring pointed at (ai/ai_router.py's multi-backend chaining): try the
local model first (free, private, no network), and only fall through to
Gemini if the local backend isn't available or its describe() call
itself fails. If neither is available, see() returns a single error
naming both, instead of only the first one tried.
"""

from typing import Optional

from skills.vision.camera_manager import get_camera_manager
from skills.vision.vision_provider import get_vision_provider
from skills.vision.remote_vision_provider import get_remote_vision_provider


class VisionEngine:
    def __init__(self):
        self._camera = get_camera_manager()
        self._local = get_vision_provider()
        self._remote = get_remote_vision_provider()

    def status(self) -> dict:
        """Availability of all three legs - a caller can use this to give
        a specific "no webcam" vs "no vision backend configured" message
        instead of one generic failure."""
        return {
            "camera_available": self._camera.is_available(),
            "vision_model_available": self._local.is_available(),
            "remote_vision_available": self._remote.is_available(),
        }

    def see(self, prompt: Optional[str] = None) -> dict:
        """Capture a frame from the camera and describe it: local model
        first, Gemini fallback if local is unavailable or fails. Returns
        {"success": True, "description": str, "snapshot_path": str,
        "backend": "local"|"remote"} or {"success": False, "error": str}
        - never raises."""
        snapshot_path = self._camera.capture_snapshot()
        if snapshot_path is None:
            return {
                "success": False,
                "error": "Could not capture a camera frame - no webcam available or opencv not installed.",
            }

        local_error = None
        if self._local.is_available():
            result = self._local.describe(snapshot_path, prompt=prompt)
            if result.get("success"):
                result["snapshot_path"] = snapshot_path
                result["backend"] = "local"
                return result
            local_error = result.get("error", "local vision model failed")

        if self._remote.is_available():
            result = self._remote.describe(snapshot_path, prompt=prompt)
            if result.get("success"):
                result["snapshot_path"] = snapshot_path
                result["backend"] = "remote"
                return result
            remote_error = result.get("error", "remote vision provider failed")
            if local_error:
                return {"success": False, "error": f"local: {local_error} | remote: {remote_error}"}
            return {"success": False, "error": remote_error}

        if local_error:
            return {"success": False, "error": local_error}
        return {
            "success": False,
            "error": "No vision backend available - local model not running and GEMINI_API_KEY not set.",
        }

    def snapshot(self, save_path: Optional[str] = None) -> dict:
        """Capture and save a photo without describing it."""
        path = self._camera.capture_snapshot(save_path=save_path)
        if path is None:
            return {
                "success": False,
                "error": "Could not capture a camera frame - no webcam available or opencv not installed.",
            }
        return {"success": True, "snapshot_path": path}


_engine: Optional[VisionEngine] = None


def get_vision_engine() -> VisionEngine:
    global _engine
    if _engine is None:
        _engine = VisionEngine()
    return _engine
