"""
skills/vision/vision_provider.py
==================================
Describes an image file via models/vision/model_manager.py's
VisionModelManager (Ollama + LLaVA today). Kept as its own module,
separate from vision_engine.py's orchestration, so a second backend
(e.g. a cloud vision API added later, the same way ai/ai_router.py
chains multiple text backends) has a single place to plug in without
touching camera_manager.py or vision_engine.py at all.

Only one concrete backend is wired today - deliberately not building
out a multi-provider fallback chain ahead of an actual second backend
existing, matching this project's own repeated finding (see
ULTRON_Phase30_Deep_Audit_Report.md) that speculative unused
abstraction is exactly what ends up orphaned.
"""

from typing import Optional

from models.vision.model_manager import get_vision_model_manager


class VisionProvider:
    """Thin facade over VisionModelManager - describe(image_path)."""

    def is_available(self) -> bool:
        return get_vision_model_manager().is_available()

    def describe(self, image_path: str, prompt: Optional[str] = None) -> dict:
        """Returns {"success": True, "description": str} or
        {"success": False, "error": str} - never raises."""
        return get_vision_model_manager().describe(image_path, prompt=prompt)


_provider: Optional[VisionProvider] = None


def get_vision_provider() -> VisionProvider:
    global _provider
    if _provider is None:
        _provider = VisionProvider()
    return _provider
