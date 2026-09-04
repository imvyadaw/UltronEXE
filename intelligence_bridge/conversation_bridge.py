"""
Conversation Bridge (Phase 20.4 - Intelligence Bridge)
==================================================
Thin, defensive bridge onto ULTRON's conversation-intelligence
subsystem under `intelligence/`, falling back to Phase 17.2's
context_bridge.py / core.context.ConversationContext (the first real
caller of conversation history in this codebase) if nothing deeper is
present. See _bridge_utils.py for the resolve-by-name/keyword +
degrade-to-no-op approach every bridge in this package shares.

Usage:
    from intelligence_bridge.conversation_bridge import get_conversation_bridge

    cvb = get_conversation_bridge()
    if cvb.is_available():
        history = cvb.get_history()

Purely additive - every method here is a best-effort call that returns
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
    "intelligence.conversation.conversation_engine",
    "intelligence.conversation",
    "intelligence.conversation_engine",
    "intelligence.conversation_intelligence",
    "cognitive_core.context_bridge",
)
_KEYWORDS = ("conversation",)
_GETTER_NAMES = ("get_conversation_engine", "get_context_bridge")
_CLASS_NAMES = ("ConversationEngine", "ContextBridge")

_FALLBACK_MODULES = ("core.context",)
_FALLBACK_GETTER_NAMES = ("get_conversation_context", "get_context")
_FALLBACK_CLASS_NAMES = ("ConversationContext",)

_MISSING = object()


class ConversationBridge:
    """Bridges to ULTRON's conversation-intelligence subsystem, falling
    back to core.context.ConversationContext (Phase 17.2) for plain
    history if nothing deeper is present."""

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
                "[conversation_bridge] connected to %s%s",
                getattr(self._module, "__name__", "?"),
                " (fallback: core.context)" if self._used_fallback else "",
            )
        else:
            logger.info("[conversation_bridge] no conversation subsystem found - running in degraded/no-op mode")

    def is_available(self) -> bool:
        return self._instance is not None

    def status(self) -> Dict[str, Any]:
        return {
            "bridge": "conversation",
            "available": self.is_available(),
            "source_module": getattr(self._module, "__name__", None),
            "used_fallback": self._used_fallback,
        }

    def get_history(self, *args, **kwargs) -> Optional[Any]:
        """Best-effort recent conversation history."""
        return first_success(
            self._instance,
            ("get_history", "history", "get_recent_turns", "get_turns"),
            *args,
            **kwargs,
        )

    def add_turn(self, role: str, text: str, *args, **kwargs) -> bool:
        """Best-effort append of a conversation turn."""
        for name in ("add_turn", "add_message", "append", "record_turn"):
            result = safe_call(self._instance, name, role, text, *args, default=_MISSING, **kwargs)
            if result is not _MISSING:
                return True
        return False

    def get_context(self, *args, **kwargs) -> Optional[Any]:
        """Best-effort current conversational context summary."""
        return first_success(
            self._instance,
            ("get_context", "context", "summary", "get_summary"),
            *args,
            **kwargs,
        )

    def call(self, method_name: str, *args, **kwargs) -> Optional[Any]:
        """Generic passthrough for anything not covered above."""
        return safe_call(self._instance, method_name, *args, **kwargs)


_bridge_instance: Optional[ConversationBridge] = None


def get_conversation_bridge() -> ConversationBridge:
    """Process-wide ConversationBridge singleton."""
    global _bridge_instance
    if _bridge_instance is None:
        _bridge_instance = ConversationBridge()
    return _bridge_instance
