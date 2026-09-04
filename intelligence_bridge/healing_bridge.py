"""
Healing Bridge (Phase 20.4 - Intelligence Bridge)
==================================================
Thin, defensive bridge onto ULTRON's self-healing/error-recovery
subsystem under `intelligence/`. See _bridge_utils.py for the
resolve-by-name/keyword + degrade-to-no-op approach every bridge in
this package shares.

Usage:
    from intelligence_bridge.healing_bridge import get_healing_bridge

    hb = get_healing_bridge()
    if hb.is_available():
        outcome = hb.attempt_repair(error, context={"operation": "youtube_play"})

Purely additive - every method here is a best-effort call that returns
None on failure instead of raising, so a caller can always try this
bridge first and fall through to its own error handling either way.
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
    "intelligence.healing.healing_engine",
    "intelligence.healing",
    "intelligence.self_healing",
    "intelligence.healing_engine",
    "intelligence.error_recovery",
)
_KEYWORDS = ("heal",)
_GETTER_NAMES = ("get_self_healing_engine", "get_healing_engine", "get_self_healing", "get_error_recovery")
_CLASS_NAMES = ("SelfHealingEngine", "HealingEngine", "SelfHealing", "ErrorRecovery")


class HealingBridge:
    """Bridges to ULTRON's self-healing / error-recovery subsystem."""

    def __init__(self):
        self._module = resolve_module(_CANDIDATE_MODULES, _KEYWORDS)
        self._instance = resolve_singleton(self._module, _GETTER_NAMES, _CLASS_NAMES)
        if self._instance is not None:
            logger.info("[healing_bridge] connected to %s", getattr(self._module, "__name__", "?"))
        else:
            logger.info("[healing_bridge] underlying module not found - running in degraded/no-op mode")

    def is_available(self) -> bool:
        return self._instance is not None

    def status(self) -> Dict[str, Any]:
        return {
            "bridge": "healing",
            "available": self.is_available(),
            "source_module": getattr(self._module, "__name__", None),
        }

    def diagnose(self, error: Any, *args, context: Optional[Dict] = None, **kwargs) -> Optional[Any]:
        """Best-effort diagnosis of what went wrong. Shims onto Phase
        19.5's get_failure_diagnoser() (via this bridge's resolved
        module) if no direct diagnose-shaped method is found on the
        main engine instance - same action-name-from-context pattern
        as attempt_repair() below."""
        call_kwargs = dict(kwargs)
        if context is not None:
            call_kwargs.setdefault("context", context)
        result = first_success(
            self._instance,
            ("diagnose", "analyze_error", "classify_error"),
            error,
            *args,
            **call_kwargs,
        )
        if result is not None:
            return result
        diagnoser_getter = getattr(self._module, "get_failure_diagnoser", None)
        if callable(diagnoser_getter):
            action_name = (context or {}).get("operation") or (context or {}).get("action") or "unknown_action"
            return safe_call(diagnoser_getter(), "diagnose", action_name, error=str(error))
        return None

    def attempt_repair(self, error: Any, *args, context: Optional[Dict] = None, **kwargs) -> Optional[Any]:
        """Best-effort automatic repair attempt for `error`. Phase
        19.5's SelfHealingEngine.heal() takes (action_name, error=...),
        not a bare error positionally, so if the generic candidates
        below don't match, this also tries heal() with the action name
        pulled from context (falling back to "unknown_action")."""
        call_kwargs = dict(kwargs)
        if context is not None:
            call_kwargs.setdefault("context", context)
        result = first_success(
            self._instance,
            ("attempt_repair", "repair", "recover", "auto_fix"),
            error,
            *args,
            **call_kwargs,
        )
        if result is not None:
            return result
        if hasattr(self._instance, "heal"):
            action_name = (context or {}).get("operation") or (context or {}).get("action") or "unknown_action"
            return safe_call(self._instance, "heal", action_name, error=str(error))
        return None

    def call(self, method_name: str, *args, **kwargs) -> Optional[Any]:
        """Generic passthrough for anything not covered above."""
        return safe_call(self._instance, method_name, *args, **kwargs)


_bridge_instance: Optional[HealingBridge] = None


def get_healing_bridge() -> HealingBridge:
    """Process-wide HealingBridge singleton."""
    global _bridge_instance
    if _bridge_instance is None:
        _bridge_instance = HealingBridge()
    return _bridge_instance
