"""
Capability Registry (Phase 21 - Unified Core Architecture)
===========================================================
Before this, "can Ultron do X" had no single answer - ai/tools_schema.py
lists LLM-callable tools, skills/*/MANIFEST.md lists skill actions, and
agents/ lists whole agents, with nothing that could be asked "do we have
a capability matching 'send email'" without a caller knowing which of
those three places to grep. action_pipeline needs that answer before it
executes anything, and autonomous_engine needs it before it commits a
goal step to a real action instead of failing at execution time - so
this is a single lookup table both consult first.

Not a dispatcher. Registering a capability records what it is and,
optionally, a handler to call - actually invoking it is
action_pipeline's job, same separation core/permissions.py already
uses for "which tools need confirmation" vs "who calls them".
"""

import threading
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

from core.logger import get_logger

logger = get_logger("ultron.capability_registry")


@dataclass
class Capability:
    name: str
    category: str  # "tool" | "skill" | "agent"
    description: str = ""
    handler: Optional[Callable] = None
    permission_level: str = "normal"  # "normal" | "elevated" | "destructive"
    enabled: bool = True
    source: str = "manual"
    metadata: Dict = field(default_factory=dict)


class CapabilityRegistry:
    """Process-wide capability index. Use get_capability_registry()."""

    def __init__(self):
        self._capabilities: Dict[str, Capability] = {}
        self._lock = threading.Lock()
        self._bootstrapped = False

    def register(
        self,
        name: str,
        category: str,
        description: str = "",
        handler: Optional[Callable] = None,
        permission_level: str = "normal",
        source: str = "manual",
        **metadata,
    ) -> Capability:
        cap = Capability(
            name=name,
            category=category,
            description=description,
            handler=handler,
            permission_level=permission_level,
            source=source,
            metadata=metadata,
        )
        with self._lock:
            self._capabilities[name] = cap
        return cap

    def unregister(self, name: str) -> bool:
        with self._lock:
            return self._capabilities.pop(name, None) is not None

    def set_enabled(self, name: str, enabled: bool) -> bool:
        with self._lock:
            cap = self._capabilities.get(name)
            if not cap:
                return False
            cap.enabled = enabled
            return True

    def has(self, name: str) -> bool:
        cap = self._capabilities.get(name)
        return bool(cap and cap.enabled)

    def get(self, name: str) -> Optional[Capability]:
        return self._capabilities.get(name)

    def list_by_category(self, category: Optional[str] = None) -> List[Capability]:
        caps = self._capabilities.values()
        if category:
            caps = [c for c in caps if c.category == category]
        return sorted(caps, key=lambda c: c.name)

    def find(self, query: str, limit: int = 5) -> List[Capability]:
        """Cheap keyword search over name + description - good enough for
        action_pipeline/autonomous_engine to shortlist candidates before
        an LLM or planner picks one; not a semantic search."""
        q = query.lower().strip()
        if not q:
            return []
        scored = []
        for cap in self._capabilities.values():
            if not cap.enabled:
                continue
            haystack = f"{cap.name} {cap.description}".lower()
            if q in haystack:
                score = haystack.count(q) + (2 if q in cap.name.lower() else 0)
                scored.append((score, cap))
        scored.sort(key=lambda pair: pair[0], reverse=True)
        return [cap for _, cap in scored[:limit]]

    # -- bootstrap from existing tool sources -----------------------------
    def bootstrap_from_tools_schema(self) -> int:
        """Best-effort: pull every LLM-callable tool from ai/tools_schema.py
        in as category='tool'. Safe to call more than once (idempotent,
        re-registers). Returns count registered."""
        try:
            from ai.tools_schema import TOOLS
        except Exception as exc:
            logger.warning(f"could not import ai.tools_schema: {exc}")
            return 0
        count = 0
        for entry in TOOLS:
            fn = entry.get("function", {})
            name = fn.get("name")
            if not name:
                continue
            self.register(
                name,
                category="tool",
                description=fn.get("description", ""),
                source="ai.tools_schema",
            )
            count += 1
        return count

    def bootstrap(self) -> None:
        """Idempotent one-shot bootstrap of everything importable at low
        cost. Heavier discovery (walking skills/ for BaseSkill subclasses)
        is deliberately left out - that requires importing every skill
        module, which can have real side effects (network clients,
        credentials); skills should self-register via register() instead."""
        if self._bootstrapped:
            return
        count = self.bootstrap_from_tools_schema()
        # Do not permanently cache a failed bootstrap. Optional dependencies
        # or platform-specific imports can be unavailable during an early
        # startup attempt and become available after environment setup.
        # Keeping _bootstrapped=False on failure allows a later real retry
        # instead of leaving the registry silently empty for the whole process.
        self._bootstrapped = count > 0


_registry: Optional[CapabilityRegistry] = None


def get_capability_registry() -> CapabilityRegistry:
    global _registry
    if _registry is None:
        _registry = CapabilityRegistry()
    return _registry
