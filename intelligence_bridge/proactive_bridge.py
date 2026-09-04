"""
Proactive Bridge (Phase 20.4 - Intelligence Bridge)
==================================================
Thin, defensive bridge onto intelligence.proactive_intelligence
(Phase 20.1) - the package that decides whether ULTRON should *say*
something unprompted, as opposed to Phase 20.2's predictive_preparation
(what to have ready) or Phase 20.3's adaptive_performance (how to make
a call fast). Package name and its urgency_calculator.py submodule are
known from Phase 20.3's own docstrings; the exact orchestrator entry
point isn't, so this still resolves defensively rather than assuming
one - see _bridge_utils.py.

Usage:
    from intelligence_bridge.proactive_bridge import get_proactive_bridge

    pb = get_proactive_bridge()
    if pb.is_available():
        decision = pb.should_speak(context={"world_state": ...})

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
    "intelligence.proactive_intelligence.proactive_engine",
    "intelligence.proactive_intelligence",
    "intelligence.proactive",
)
_KEYWORDS = ("proactive",)
_GETTER_NAMES = ("get_proactive_engine", "get_proactive_intelligence")
_CLASS_NAMES = ("ProactiveEngine", "ProactiveIntelligence")


class ProactiveBridge:
    """Bridges to intelligence.proactive_intelligence (Phase 20.1)."""

    def __init__(self):
        self._module = resolve_module(_CANDIDATE_MODULES, _KEYWORDS)
        self._instance = resolve_singleton(self._module, _GETTER_NAMES, _CLASS_NAMES)
        if self._instance is not None:
            logger.info("[proactive_bridge] connected to %s", getattr(self._module, "__name__", "?"))
        else:
            logger.info("[proactive_bridge] proactive_intelligence not found - running in degraded/no-op mode")

    def is_available(self) -> bool:
        return self._instance is not None

    def status(self) -> Dict[str, Any]:
        return {
            "bridge": "proactive",
            "available": self.is_available(),
            "source_module": getattr(self._module, "__name__", None),
        }

    def should_speak(self, context: Optional[Dict] = None, *args, **kwargs) -> Optional[Any]:
        """Best-effort "is now a good moment to say something unprompted"
        check. Phase 20.1's ProactiveEngine has no should_speak/evaluate
        method - its one entry point is process_signal(raw_signal,
        context=...), built for an actual event (app closed, timer
        fired, etc), not a bare conversational context. So if the
        generic candidates below don't match, this wraps `context` as
        a minimal signal and lets event_detector.py decide for itself
        whether that's event-shaped enough to act on (returning
        has_event=False for an unrecognized signal is a normal,
        correct "no" here, not a failure)."""
        result = first_success(
            self._instance,
            ("should_speak", "evaluate", "should_notify", "check"),
            context,
            *args,
            **kwargs,
        )
        if result is not None:
            return result
        if hasattr(self._instance, "process_signal"):
            raw_signal = {"type": "conversation_turn", "context": context or {}}
            return safe_call(self._instance, "process_signal", raw_signal, context=context)
        return None

    def get_urgency(self, context: Optional[Dict] = None, *args, **kwargs) -> Optional[Any]:
        """Best-effort urgency score, mirroring urgency_calculator.py's role."""
        return first_success(
            self._instance,
            ("get_urgency", "calculate_urgency", "urgency"),
            context,
            *args,
            **kwargs,
        )

    def call(self, method_name: str, *args, **kwargs) -> Optional[Any]:
        """Generic passthrough for anything not covered above."""
        return safe_call(self._instance, method_name, *args, **kwargs)


_bridge_instance: Optional[ProactiveBridge] = None


def get_proactive_bridge() -> ProactiveBridge:
    """Process-wide ProactiveBridge singleton."""
    global _bridge_instance
    if _bridge_instance is None:
        _bridge_instance = ProactiveBridge()
    return _bridge_instance
