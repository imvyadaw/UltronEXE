"""
Screen Analyzer (Phase 22 - Perception)
========================================
Normalizes "look at the screen" into one perception event. Two tiers,
cheapest capable one wins unless a caller asks otherwise:

  1. vision/vision_llm.py's describe_screen() - a real multimodal read
     (Gemini) when GEMINI_API_KEY is configured; best quality, costs an
     API call.
  2. vision/screen/capture.py + vision/ocr - plain OCR text dump as a
     free, fully-offline fallback when no vision-LLM key is set or the
     call fails. Coarser (no layout/semantic understanding) but keeps
     "what's on screen" answerable with zero configuration.

Either path returns through the same {"description"|"text", ...} shape
so callers (action_pipeline's "perceive_screen" capability,
autonomous_engine deciding whether a step already happened) don't need
to know which tier answered.
"""

import time
from typing import Dict, Optional

from core.logger import get_logger

logger = get_logger("ultron.perception.screen_analyzer")


class ScreenAnalyzer:
    def analyze(self, question: str = "Describe what's currently on screen.", prefer_llm: bool = True) -> Dict:
        data = None
        if prefer_llm:
            data = self._analyze_with_vision_llm(question)
        if data is None:
            data = self._analyze_with_ocr()
        if data is None:
            data = {"available": False, "reason": "no vision backend available"}
        return self._emit(data)

    def locate(self, target: str) -> Dict:
        """Where on screen something is, in pixel coordinates - needs the
        vision-LLM tier; no OCR-only fallback (OCR alone can't ground
        non-text UI elements)."""
        try:
            from vision.vision_llm import VisionLLM

            result = VisionLLM().locate_on_screen(target)
            return self._emit({"available": True, "target": target, **result}, event_name="perception.screen_locate")
        except Exception as exc:
            logger.debug(f"screen_analyzer: locate unavailable: {exc}")
            return self._emit(
                {"available": False, "target": target, "reason": str(exc)}, event_name="perception.screen_locate"
            )

    # -- tiers ---------------------------------------------------------
    def _analyze_with_vision_llm(self, question: str) -> Optional[Dict]:
        try:
            from vision.vision_llm import VisionLLM

            result = VisionLLM().describe_screen(question)
            if isinstance(result, dict) and not result.get("error"):
                return {"available": True, "tier": "vision_llm", **result}
            logger.debug(f"screen_analyzer: vision_llm returned error: {result}")
        except Exception as exc:
            logger.debug(f"screen_analyzer: vision_llm unavailable: {exc}")
        return None

    def _analyze_with_ocr(self) -> Optional[Dict]:
        try:
            from vision.ocr.tesseract_ocr import TesseractOCR

            result = TesseractOCR().read_screen()
            if isinstance(result, dict) and not result.get("error"):
                return {"available": True, "tier": "ocr", **result}
        except Exception as exc:
            logger.debug(f"screen_analyzer: OCR fallback unavailable: {exc}")
        return None

    # -- emit ----------------------------------------------------------
    def _emit(self, data: Dict, event_name: str = "perception.screen") -> Dict:
        event = {"modality": "screen", "timestamp": time.time(), "data": data, "source": "screen_analyzer"}
        try:
            from core.event_bus import get_event_bus

            get_event_bus().emit(event_name, **event)
        except Exception:
            from core.error_trace import log_swallowed as _lsw

            _lsw("perception.screen_analyzer._emit")
        return event


_analyzer: Optional[ScreenAnalyzer] = None


def get_screen_analyzer() -> ScreenAnalyzer:
    global _analyzer
    if _analyzer is None:
        _analyzer = ScreenAnalyzer()
    return _analyzer
