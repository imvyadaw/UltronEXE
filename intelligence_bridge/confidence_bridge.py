"""
Confidence Bridge (Phase 20.4 - Intelligence Bridge)
==================================================
Thin, defensive bridge onto ULTRON's confidence-scoring subsystem
under `intelligence/` - whatever decides how sure ULTRON should be in
an answer before speaking it, or whether it should ask a clarifying
question instead. See _bridge_utils.py for the resolve-by-name/keyword
+ degrade-to-no-op approach every bridge in this package shares.

Usage:
    from intelligence_bridge.confidence_bridge import get_confidence_bridge

    cb = get_confidence_bridge()
    if cb.is_available():
        score = cb.score(answer, context={"question": "..."})

Purely additive - every method here is a best-effort call that returns
None on failure instead of raising. A caller with no better signal can
treat a None score as "unknown" rather than "low confidence".
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
    "intelligence.confidence.confidence_engine",
    "intelligence.confidence",
    "intelligence.confidence_engine",
    "intelligence.confidence_scoring",
)
_KEYWORDS = ("confidence",)
_GETTER_NAMES = ("get_decision_gate", "get_confidence_engine", "get_confidence_scorer")
_CLASS_NAMES = ("DecisionGate", "ConfidenceEngine", "ConfidenceScorer")


class ConfidenceBridge:
    """Bridges to ULTRON's confidence-scoring subsystem."""

    def __init__(self):
        self._module = resolve_module(_CANDIDATE_MODULES, _KEYWORDS)
        self._instance = resolve_singleton(self._module, _GETTER_NAMES, _CLASS_NAMES)
        if self._instance is not None:
            logger.info("[confidence_bridge] connected to %s", getattr(self._module, "__name__", "?"))
        else:
            logger.info("[confidence_bridge] underlying module not found - running in degraded/no-op mode")

    def is_available(self) -> bool:
        return self._instance is not None

    def status(self) -> Dict[str, Any]:
        return {
            "bridge": "confidence",
            "available": self.is_available(),
            "source_module": getattr(self._module, "__name__", None),
        }

    def score(self, answer: Any, *args, context: Optional[Dict] = None, **kwargs) -> Optional[Any]:
        """Best-effort confidence score (0-1 or subsystem-defined) for
        `answer`. Phase 19.8 doesn't score a free-form answer directly
        - get_confidence_calculator().calculate(signals) does, given a
        named signals dict - so if the generic candidates below don't
        match, this also tries that via the resolved module, using
        context["signals"] if the caller supplied one (empty signals
        is a safe, defined no-op there: returns a neutral 0.5 rather
        than raising)."""
        call_kwargs = dict(kwargs)
        if context is not None:
            call_kwargs.setdefault("context", context)
        result = first_success(
            self._instance,
            ("score", "get_confidence", "evaluate", "rate"),
            answer,
            *args,
            **call_kwargs,
        )
        if result is not None:
            return result
        calculator_getter = getattr(self._module, "get_confidence_calculator", None)
        if callable(calculator_getter):
            signals = (context or {}).get("signals", {}) if isinstance(context, dict) else {}
            return safe_call(calculator_getter(), "calculate", signals)
        return None

    def should_clarify(self, context: Optional[Dict] = None, *args, **kwargs) -> Optional[Any]:
        """Best-effort "is confidence low enough to ask a clarifying
        question instead" check. Shims onto DecisionGate.decide() (the
        real Phase 19.8 entry point) if no direct should_clarify-shaped
        method is found. Only does this when the caller actually
        supplied context["signals"] - with no signals, decide() always
        lands on a neutral 0.5 (below its auto-execute bar), which
        would make this return True on every single call regardless of
        real confidence. No signal is "I don't know", not "clarify"."""
        result = first_success(
            self._instance,
            ("should_clarify", "should_ask_clarifying", "needs_clarification"),
            context,
            *args,
            **kwargs,
        )
        if result is not None:
            return result
        signals = (context or {}).get("signals") if isinstance(context, dict) else None
        if signals and hasattr(self._instance, "decide"):
            action_name = (context or {}).get("intent") or "respond"
            decision = safe_call(self._instance, "decide", str(action_name), signals, context=context)
            if isinstance(decision, dict) and "decision" in decision:
                return decision["decision"] != "auto_execute"
        return None

    def call(self, method_name: str, *args, **kwargs) -> Optional[Any]:
        """Generic passthrough for anything not covered above."""
        return safe_call(self._instance, method_name, *args, **kwargs)


_bridge_instance: Optional[ConfidenceBridge] = None


def get_confidence_bridge() -> ConfidenceBridge:
    """Process-wide ConfidenceBridge singleton."""
    global _bridge_instance
    if _bridge_instance is None:
        _bridge_instance = ConfidenceBridge()
    return _bridge_instance
