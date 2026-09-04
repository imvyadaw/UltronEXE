"""
Answer Reader Bridge (Phase 20.4 - Intelligence Bridge)
==================================================
Thin, defensive bridge onto ULTRON's answer-reader subsystem under
`intelligence/` - whatever extracts a direct, speakable answer out of
a larger source (a search result, a scraped page, a long tool output)
rather than reading the whole thing back to the user. See
_bridge_utils.py for the resolve-by-name/keyword + degrade-to-no-op
approach every bridge in this package shares.

Usage:
    from intelligence_bridge.answer_reader_bridge import get_answer_reader_bridge

    arb = get_answer_reader_bridge()
    if arb.is_available():
        answer = arb.extract_answer(page_text, question="capital of France")

Purely additive - every method here is a best-effort call that returns
None on failure instead of raising.
"""

from typing import Any, Dict, Optional

from intelligence_bridge._bridge_utils import (
    first_success,
    resolve_module,
    resolve_singleton,
    safe_call,
    logger,
)

_CANDIDATE_MODULES = (
    "intelligence.answer_reader.answer_reader_engine",
    "intelligence.answer_reader",
    "intelligence.answer_reader_engine",
    "intelligence.answer_reading",
)
_KEYWORDS = ("answer",)
_GETTER_NAMES = ("get_answer_reader_engine", "get_answer_reader", "get_answer_extractor")
_CLASS_NAMES = ("AnswerReaderEngine", "AnswerReader", "AnswerExtractor")


class AnswerReaderBridge:
    """Bridges to ULTRON's answer-extraction subsystem."""

    def __init__(self):
        self._module = resolve_module(_CANDIDATE_MODULES, _KEYWORDS)
        self._instance = resolve_singleton(self._module, _GETTER_NAMES, _CLASS_NAMES)
        if self._instance is not None:
            logger.info("[answer_reader_bridge] connected to %s", getattr(self._module, "__name__", "?"))
        else:
            logger.info("[answer_reader_bridge] underlying module not found - running in degraded/no-op mode")

    def is_available(self) -> bool:
        return self._instance is not None

    def status(self) -> Dict[str, Any]:
        return {
            "bridge": "answer_reader",
            "available": self.is_available(),
            "source_module": getattr(self._module, "__name__", None),
        }

    def extract_answer(self, source_text: str, *args, question: Optional[str] = None, **kwargs) -> Optional[Any]:
        """Best-effort short, speakable answer pulled from `source_text`.
        Phase 19.9's AnswerReaderEngine.read(text, mode=...) doesn't take
        a `question` kwarg - it's a length/summarize pipeline, not a
        QA extractor - so if the generic candidates below don't match,
        this also tries read(source_text) directly and returns its
        primary_text/speakable_text."""
        call_kwargs = dict(kwargs)
        if question is not None:
            call_kwargs.setdefault("question", question)
        result = first_success(
            self._instance,
            ("extract_answer", "extract", "answer_from"),
            source_text,
            *args,
            **call_kwargs,
        )
        if result is not None:
            return result
        if hasattr(self._instance, "read"):
            read_result = safe_call(self._instance, "read", source_text)
            if isinstance(read_result, dict):
                return read_result.get("speakable_text") or read_result.get("primary_text") or read_result
            return read_result
        return None

    def call(self, method_name: str, *args, **kwargs) -> Optional[Any]:
        """Generic passthrough for anything not covered above."""
        return safe_call(self._instance, method_name, *args, **kwargs)


_bridge_instance: Optional[AnswerReaderBridge] = None


def get_answer_reader_bridge() -> AnswerReaderBridge:
    """Process-wide AnswerReaderBridge singleton."""
    global _bridge_instance
    if _bridge_instance is None:
        _bridge_instance = AnswerReaderBridge()
    return _bridge_instance
