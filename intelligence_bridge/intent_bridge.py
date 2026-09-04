"""
Intent Bridge (Phase 20.4 - Intelligence Bridge)
==================================================
Thin, defensive bridge onto ULTRON's deeper intent-understanding
subsystem under `intelligence/` (distinct from core.intent_router's
fast structural classifier from Phase 17.2 - this targets whatever
later phase added richer intent modelling on top of it). See
_bridge_utils.py for the resolve-by-name/keyword + degrade-to-no-op
approach every bridge in this package shares.

Usage:
    from intelligence_bridge.intent_bridge import get_intent_bridge

    ib = get_intent_bridge()
    if ib.is_available():
        result = ib.classify("play some music")

Purely additive - every method here is a best-effort call that returns
None on failure instead of raising, and falls back to core.intent_router
only as a last resort so a caller always gets *something* usable even
in a checkout where the deeper intelligence/-level module isn't present.
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
    "intelligence.intent.intent_engine",
    "intelligence.intent",
    "intelligence.intent_engine",
    "intelligence.intent_understanding",
)
_KEYWORDS = ("intent",)
_GETTER_NAMES = ("get_intent_predictor", "get_intent_engine", "get_intent_understanding")
_CLASS_NAMES = ("IntentPredictor", "IntentEngine", "IntentUnderstanding", "IntentAnalyzer")

_FALLBACK_MODULES = ("core.intent_router",)
_FALLBACK_GETTER_NAMES = ("get_intent_router", "get_router")
_FALLBACK_CLASS_NAMES = ("IntentRouter",)


class IntentBridge:
    """Bridges to ULTRON's intelligence-layer intent subsystem, falling
    back to core.intent_router (Phase 17.2's structural classifier) if
    nothing deeper is present."""

    def __init__(self):
        self._module = resolve_module(_CANDIDATE_MODULES, _KEYWORDS)
        self._instance = resolve_singleton(self._module, _GETTER_NAMES, _CLASS_NAMES)
        self._used_fallback = False

        if self._instance is None:
            fallback_module = resolve_module(_FALLBACK_MODULES)
            fallback_instance = resolve_singleton(
                fallback_module,
                _FALLBACK_GETTER_NAMES,
                _FALLBACK_CLASS_NAMES,
            )
            if fallback_instance is not None:
                self._module, self._instance = fallback_module, fallback_instance
                self._used_fallback = True

        if self._instance is not None:
            logger.info(
                "[intent_bridge] connected to %s%s",
                getattr(self._module, "__name__", "?"),
                " (fallback: core.intent_router)" if self._used_fallback else "",
            )
        else:
            logger.info("[intent_bridge] no intent subsystem found - running in degraded/no-op mode")

    def is_available(self) -> bool:
        return self._instance is not None

    def status(self) -> Dict[str, Any]:
        return {
            "bridge": "intent",
            "available": self.is_available(),
            "source_module": getattr(self._module, "__name__", None),
            "used_fallback": self._used_fallback,
        }

    def classify(self, text: str, *args, **kwargs) -> Optional[Any]:
        """Best-effort intent classification for `text`. Phase 19.2's
        IntentPredictor doesn't classify raw text directly - it predicts
        from ambient context (recent actions, world state), so if the
        generic text-in candidates below don't match, this also tries
        predict(context=...) using whatever context the caller passed,
        which is the real shape that subsystem expects."""
        result = first_success(
            self._instance,
            ("classify", "resolve", "understand", "analyze", "detect_intent"),
            text,
            *args,
            **kwargs,
        )
        if result is not None:
            return result
        if hasattr(self._instance, "predict"):
            return safe_call(self._instance, "predict", context=kwargs.get("context"))
        return None

    def get_confidence(self, text: str, *args, **kwargs) -> Optional[Any]:
        """Best-effort confidence score for the last/given classification."""
        return first_success(
            self._instance,
            ("get_confidence", "confidence", "score"),
            text,
            *args,
            **kwargs,
        )

    def call(self, method_name: str, *args, **kwargs) -> Optional[Any]:
        """Generic passthrough for anything not covered above."""
        return safe_call(self._instance, method_name, *args, **kwargs)


_bridge_instance: Optional[IntentBridge] = None


def get_intent_bridge() -> IntentBridge:
    """Process-wide IntentBridge singleton."""
    global _bridge_instance
    if _bridge_instance is None:
        _bridge_instance = IntentBridge()
    return _bridge_instance
