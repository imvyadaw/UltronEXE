"""
Verification Bridge (Phase 20.4 - Intelligence Bridge)
==================================================
Thin, defensive bridge onto ULTRON's result-verification subsystem -
either a later intelligence/-level module, or (falling back) Phase
17.2's self_critique_agent.py, which already judges whether a goal was
actually achieved rather than just "steps succeeded". See
_bridge_utils.py for the resolve-by-name/keyword + degrade-to-no-op
approach every bridge in this package shares.

Usage:
    from intelligence_bridge.verification_bridge import get_verification_bridge

    vb = get_verification_bridge()
    if vb.is_available():
        verdict = vb.verify("the file was saved", context={"path": "..."})

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
    "intelligence.verification.verification_engine",
    "intelligence.verification",
    "intelligence.verification_engine",
    "intelligence.self_verification",
    "cognitive_core.self_critique_agent",
)
_KEYWORDS = ("verif",)
_GETTER_NAMES = ("get_verification_engine", "get_self_critique_agent", "get_verifier")
_CLASS_NAMES = ("VerificationEngine", "SelfCritiqueAgent", "Verifier")


class VerificationBridge:
    """Bridges to ULTRON's result-verification / self-critique subsystem."""

    def __init__(self):
        self._module = resolve_module(_CANDIDATE_MODULES, _KEYWORDS)
        self._instance = resolve_singleton(self._module, _GETTER_NAMES, _CLASS_NAMES)
        if self._instance is not None:
            logger.info("[verification_bridge] connected to %s", getattr(self._module, "__name__", "?"))
        else:
            logger.info("[verification_bridge] underlying module not found - running in degraded/no-op mode")

    def is_available(self) -> bool:
        return self._instance is not None

    def status(self) -> Dict[str, Any]:
        return {
            "bridge": "verification",
            "available": self.is_available(),
            "source_module": getattr(self._module, "__name__", None),
        }

    def verify(self, claim: str, *args, context: Optional[Dict] = None, **kwargs) -> Optional[Any]:
        """Best-effort verdict on whether `claim` actually holds."""
        call_kwargs = dict(kwargs)
        if context is not None:
            call_kwargs.setdefault("context", context)
        return first_success(
            self._instance,
            ("verify", "check", "critique", "evaluate"),
            claim,
            *args,
            **call_kwargs,
        )

    def is_achieved(self, goal_text: str, result: Any, *args, **kwargs) -> Optional[Any]:
        """Best-effort "was this goal actually achieved" judgment."""
        return first_success(
            self._instance,
            ("is_achieved", "was_achieved", "judge", "critique_result"),
            goal_text,
            result,
            *args,
            **kwargs,
        )

    def call(self, method_name: str, *args, **kwargs) -> Optional[Any]:
        """Generic passthrough for anything not covered above."""
        return safe_call(self._instance, method_name, *args, **kwargs)


_bridge_instance: Optional[VerificationBridge] = None


def get_verification_bridge() -> VerificationBridge:
    """Process-wide VerificationBridge singleton."""
    global _bridge_instance
    if _bridge_instance is None:
        _bridge_instance = VerificationBridge()
    return _bridge_instance
