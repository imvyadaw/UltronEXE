"""
models/vision/model_config.py
==============================
VisionModelConfig - a plain dataclass shape for model_manager.py to
construct VisionModelLoader (loader.py) from, sourced from root
config.py's VISION_* settings (not a config/vision_config.py submodule -
config.py already shadows the config/ directory as the `config` import
target project-wide; see config.py's own comment above those settings
for why).

Kept as its own small file, matching this package's one-file-per-concern
split: loader.py is the HTTP client, model_config.py is what to construct
it with, model_manager.py is the lazy singleton + caller-facing API.
"""

from dataclasses import dataclass

from config import (
    VISION_MODEL_HOST,
    VISION_MODEL_NAME,
    VISION_MODEL_TIMEOUT_S,
    VISION_DEFAULT_PROMPT,
)


@dataclass(frozen=True)
class VisionModelConfig:
    host: str = VISION_MODEL_HOST
    model: str = VISION_MODEL_NAME
    timeout_s: int = VISION_MODEL_TIMEOUT_S
    default_prompt: str = VISION_DEFAULT_PROMPT


DEFAULT_VISION_MODEL_CONFIG = VisionModelConfig()
