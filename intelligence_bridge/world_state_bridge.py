"""
World State Bridge (Phase 20.4 - Intelligence Bridge)
==================================================
Thin, defensive bridge onto whatever module elsewhere in `intelligence/`
owns ULTRON's model of "what's true right now" (active app/window,
user presence, open documents, current time-of-day context, etc). See
_bridge_utils.py for why this bridge resolves its target by name/
keyword at runtime instead of a hard import, and degrades to a
harmless no-op if that target isn't present in a given checkout.

Usage:
    from intelligence_bridge.world_state_bridge import get_world_state_bridge

    ws = get_world_state_bridge()
    if ws.is_available():
        state = ws.get_state()

Purely additive - does not modify or require the underlying world-state
module; every method here is a best-effort read/write that returns
None/False on failure instead of raising.
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
    "intelligence.world_state.world_state_engine",
    "intelligence.world_state",
    "intelligence.world_state_engine",
    "intelligence.world_awareness",
    "intelligence.situational_awareness",
)
_KEYWORDS = ("world", "state")
_GETTER_NAMES = ("get_world_state_manager", "get_world_state", "get_world_state_engine", "get_world_model")
_CLASS_NAMES = ("WorldStateManager", "WorldStateEngine", "WorldState", "WorldModel")

_MISSING = object()


class WorldStateBridge:
    """Bridges to ULTRON's world-state subsystem, if present."""

    def __init__(self):
        self._module = resolve_module(_CANDIDATE_MODULES, _KEYWORDS)
        self._instance = resolve_singleton(self._module, _GETTER_NAMES, _CLASS_NAMES)
        if self._instance is not None:
            logger.info("[world_state_bridge] connected to %s", getattr(self._module, "__name__", "?"))
        else:
            logger.info("[world_state_bridge] underlying module not found - running in degraded/no-op mode")

    def is_available(self) -> bool:
        return self._instance is not None

    def status(self) -> Dict[str, Any]:
        return {
            "bridge": "world_state",
            "available": self.is_available(),
            "source_module": getattr(self._module, "__name__", None),
        }

    def get_state(self, *args, **kwargs) -> Optional[Any]:
        """Best-effort snapshot of current world state."""
        return first_success(
            self._instance,
            ("get_state", "get_world_state", "snapshot", "get_snapshot", "current_state"),
            *args,
            **kwargs,
        )

    def get_context(self, *args, **kwargs) -> Optional[Any]:
        """Best-effort contextual summary (active app, presence, etc)."""
        return first_success(
            self._instance,
            ("get_context", "describe", "summary", "get_summary"),
            *args,
            **kwargs,
        )

    def update_state(self, key: str, value: Any) -> bool:
        """Best-effort write. Returns True only if a known update method
        actually accepted the call."""
        for name in ("update_state", "set_state", "update", "set"):
            result = safe_call(self._instance, name, key, value, default=_MISSING)
            if result is not _MISSING:
                return True
        return False

    def call(self, method_name: str, *args, **kwargs) -> Optional[Any]:
        """Generic passthrough for anything not covered above."""
        return safe_call(self._instance, method_name, *args, **kwargs)


_bridge_instance: Optional[WorldStateBridge] = None


def get_world_state_bridge() -> WorldStateBridge:
    """Process-wide WorldStateBridge singleton."""
    global _bridge_instance
    if _bridge_instance is None:
        _bridge_instance = WorldStateBridge()
    return _bridge_instance
