"""
Skill Learning Bridge (Phase 20.4 - Intelligence Bridge)
==================================================
Thin, defensive bridge onto ULTRON's skill-learning subsystem under
`intelligence/` - whatever tracks which skills/tools tend to succeed
for which kind of request and feeds that back into future choices.
See _bridge_utils.py for the resolve-by-name/keyword + degrade-to-no-op
approach every bridge in this package shares.

Usage:
    from intelligence_bridge.skill_learning_bridge import get_skill_learning_bridge

    slb = get_skill_learning_bridge()
    if slb.is_available():
        slb.record_outcome("youtube_play", success=True, context={"query": "..."})

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
    "intelligence.skill_learning.skill_learning_engine",
    "intelligence.skill_learning",
    "intelligence.skill_learning_engine",
    "intelligence.skill_acquisition",
)
_KEYWORDS = ("skill",)
_GETTER_NAMES = ("get_skill_builder_engine", "get_skill_learning_engine", "get_skill_learner")
_CLASS_NAMES = ("SkillBuilderEngine", "SkillLearningEngine", "SkillLearner")

_MISSING = object()


class SkillLearningBridge:
    """Bridges to ULTRON's skill-learning subsystem."""

    def __init__(self):
        self._module = resolve_module(_CANDIDATE_MODULES, _KEYWORDS)
        self._instance = resolve_singleton(self._module, _GETTER_NAMES, _CLASS_NAMES)
        if self._instance is not None:
            logger.info("[skill_learning_bridge] connected to %s", getattr(self._module, "__name__", "?"))
        else:
            logger.info("[skill_learning_bridge] underlying module not found - running in degraded/no-op mode")

    def is_available(self) -> bool:
        return self._instance is not None

    def status(self) -> Dict[str, Any]:
        return {
            "bridge": "skill_learning",
            "available": self.is_available(),
            "source_module": getattr(self._module, "__name__", None),
        }

    def record_outcome(self, skill: str, success: bool, *args, context: Optional[Dict] = None, **kwargs) -> bool:
        """Best-effort log of whether `skill` succeeded this time."""
        call_kwargs = dict(kwargs)
        if context is not None:
            call_kwargs.setdefault("context", context)
        for name in ("record_outcome", "record", "log_outcome", "log_result"):
            result = safe_call(self._instance, name, skill, success, *args, default=_MISSING, **call_kwargs)
            if result is not _MISSING:
                return True
        return False

    def suggest_skill(self, context: Optional[Dict] = None, *args, **kwargs) -> Optional[Any]:
        """Best-effort suggestion for which skill/tool fits `context` best."""
        return first_success(
            self._instance,
            ("suggest_skill", "suggest", "recommend", "best_skill_for"),
            context,
            *args,
            **kwargs,
        )

    def call(self, method_name: str, *args, **kwargs) -> Optional[Any]:
        """Generic passthrough for anything not covered above."""
        return safe_call(self._instance, method_name, *args, **kwargs)


_bridge_instance: Optional[SkillLearningBridge] = None


def get_skill_learning_bridge() -> SkillLearningBridge:
    """Process-wide SkillLearningBridge singleton."""
    global _bridge_instance
    if _bridge_instance is None:
        _bridge_instance = SkillLearningBridge()
    return _bridge_instance
