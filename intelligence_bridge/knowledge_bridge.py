"""
Knowledge Bridge (Phase 20.4 - Intelligence Bridge)
==================================================
Thin, defensive bridge onto ULTRON's knowledge-base subsystem under
`intelligence/`, and (falling back) core.memory from Phase 17.2 for
plain recall if nothing deeper is present. See _bridge_utils.py for
the resolve-by-name/keyword + degrade-to-no-op approach every bridge
in this package shares.

Usage:
    from intelligence_bridge.knowledge_bridge import get_knowledge_bridge

    kb = get_knowledge_bridge()
    if kb.is_available():
        fact = kb.query("what's the wifi password")

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
    "intelligence.knowledge.knowledge_engine",
    "intelligence.knowledge",
    "intelligence.knowledge_engine",
    "intelligence.knowledge_base",
)
_KEYWORDS = ("knowledge",)
_GETTER_NAMES = ("get_knowledge_graph_engine", "get_knowledge_engine", "get_knowledge_base")
_CLASS_NAMES = ("KnowledgeGraphEngine", "KnowledgeEngine", "KnowledgeBase")

_FALLBACK_MODULES = ("core.memory",)
_FALLBACK_GETTER_NAMES = ("get_memory",)
_FALLBACK_CLASS_NAMES = ("Memory",)


class KnowledgeBridge:
    """Bridges to ULTRON's knowledge-base subsystem, falling back to
    core.memory (Phase 17.2) for plain recall if nothing deeper is present."""

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
                "[knowledge_bridge] connected to %s%s",
                getattr(self._module, "__name__", "?"),
                " (fallback: core.memory)" if self._used_fallback else "",
            )
        else:
            logger.info("[knowledge_bridge] no knowledge subsystem found - running in degraded/no-op mode")

    def is_available(self) -> bool:
        return self._instance is not None

    def status(self) -> Dict[str, Any]:
        return {
            "bridge": "knowledge",
            "available": self.is_available(),
            "source_module": getattr(self._module, "__name__", None),
            "used_fallback": self._used_fallback,
        }

    def query(self, question: str, *args, **kwargs) -> Optional[Any]:
        """Best-effort answer/lookup for `question`. Phase 19.7's
        KnowledgeGraphEngine.search(query, limit=10) doesn't take a
        `context` kwarg the way the generic candidates below assume,
        so this drops it before trying "search" specifically."""
        result = first_success(
            self._instance,
            ("query", "ask", "recall", "lookup"),
            question,
            *args,
            **kwargs,
        )
        if result is not None:
            return result
        return safe_call(self._instance, "search", question)

    def remember(self, fact: str, *args, **kwargs) -> bool:
        """Best-effort store of `fact` for later recall."""
        for name in ("remember", "store", "add_fact", "save", "ingest"):
            result = safe_call(self._instance, name, fact, *args, default=_MISSING, **kwargs)
            if result is not _MISSING:
                return True
        return False

    def call(self, method_name: str, *args, **kwargs) -> Optional[Any]:
        """Generic passthrough for anything not covered above."""
        return safe_call(self._instance, method_name, *args, **kwargs)


_MISSING = object()
_bridge_instance: Optional[KnowledgeBridge] = None


def get_knowledge_bridge() -> KnowledgeBridge:
    """Process-wide KnowledgeBridge singleton."""
    global _bridge_instance
    if _bridge_instance is None:
        _bridge_instance = KnowledgeBridge()
    return _bridge_instance
