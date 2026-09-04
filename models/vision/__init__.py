"""
models/vision/ - category namespace for local vision *models* (e.g. a
locally-run vision-language model), as opposed to vision/'s OpenCV/YOLO/
Tesseract-based analysis which needs no downloaded model.

loader.py is the thin Ollama+LLaVA HTTP client. model_config.py sources
its construction args (host/model/timeout) from config/vision_config.py.
model_manager.py is now the wired-up entry point - get_vision_model_manager()
- used by skills/vision/vision_provider.py; loader.py's own docstring
previously said "nothing imports it yet", that's no longer true.
"""

from models.vision.loader import VisionModelLoader
from models.vision.model_config import VisionModelConfig, DEFAULT_VISION_MODEL_CONFIG
from models.vision.model_manager import VisionModelManager, get_vision_model_manager

__all__ = [
    "VisionModelLoader",
    "VisionModelConfig",
    "DEFAULT_VISION_MODEL_CONFIG",
    "VisionModelManager",
    "get_vision_model_manager",
]
