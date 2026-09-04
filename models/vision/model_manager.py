"""
models/vision/model_manager.py
================================
Wires up VisionModelLoader (loader.py) - which, per its own docstring,
"nothing imports... yet". This is that: a lazy singleton
(get_vision_model_manager(), matching eyes/live_camera.py's
get_live_camera() convention) plus a caller-facing API that returns
{"success": ..., ...} dicts instead of raising, so skills/vision/
vision_provider.py and ai/vision_skill_tools.py's handlers don't each
need their own try/except around loader.describe_image()'s RuntimeError.

No new vision-model logic lives here - describe()/is_available() just
delegate to VisionModelLoader, constructed from VisionModelConfig
(model_config.py) instead of loader.py's own hardcoded defaults.
"""

from typing import Optional

from models.vision.loader import VisionModelLoader
from models.vision.model_config import DEFAULT_VISION_MODEL_CONFIG, VisionModelConfig


class VisionModelManager:
    """Caller-facing wrapper over VisionModelLoader - construct with a
    VisionModelConfig, then call describe()/is_available()."""

    def __init__(self, cfg: Optional[VisionModelConfig] = None):
        self.cfg = cfg or DEFAULT_VISION_MODEL_CONFIG
        self._loader = VisionModelLoader(host=self.cfg.host, model=self.cfg.model)

    def is_available(self) -> bool:
        return self._loader.is_available()

    def describe(self, image_path: str, prompt: Optional[str] = None) -> dict:
        """Describe the image at image_path. Never raises - a failed
        describe_image() call (server down, model not pulled, bad path)
        comes back as {"success": False, "error": ...} instead of an
        exception, matching this project's skill-result convention."""
        if not self.is_available():
            return {
                "success": False,
                "error": (
                    f"Vision model '{self.cfg.model}' not available at {self.cfg.host} - "
                    "is `ollama serve` running with that model pulled?"
                ),
            }
        try:
            text = self._loader.describe_image(image_path, prompt or self.cfg.default_prompt)
            return {"success": True, "description": text}
        except RuntimeError as exc:
            return {"success": False, "error": str(exc)}


_manager: Optional[VisionModelManager] = None


def get_vision_model_manager() -> VisionModelManager:
    """Process-wide VisionModelManager singleton."""
    global _manager
    if _manager is None:
        _manager = VisionModelManager()
    return _manager
