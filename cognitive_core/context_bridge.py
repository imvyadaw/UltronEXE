"""
Context bridge
===============
The cognitive layer's one window onto "what's going on right now",
built from three things that already exist but were never wired
together:

    core.context.ConversationContext  - active app / cwd / recent tool
                                         results (defined in Phase 9,
                                         never actually instantiated
                                         anywhere - this is its first
                                         real caller, unmodified)
    core.memory.MemoryStore           - long-term + vector recall
    PHASE_17_1_FOUNDATION's bridge    - unified event bus + config

Every stage of goal_planner / task_decomposer / self_critique_agent /
autonomous_executor reports through here instead of importing the
event bus directly, so cognition is observable on one namespace:
"cognition:started", "cognition:subgoal", "cognition:step",
"cognition:critique", "cognition:complete" - a future dashboard panel
can subscribe to "cognition:*" on the unified bus and watch a goal
run live without touching any of the COGNITIVE_CORE modules directly.
"""

from threading import Lock
from typing import Any, Dict, Optional

from core.context import ConversationContext
from core.memory import MemoryStore

from core_integration.phase16_bridge import get_bridge

_context_bridge: Optional["CognitiveContextBridge"] = None
_lock = Lock()


class CognitiveContextBridge:
    """Do not construct directly - use get_context_bridge()."""

    def __init__(self):
        self._phase16 = get_bridge()
        self._conversation = ConversationContext()
        self._memory = MemoryStore()

    # -- situational snapshot ----------------------------------------------
    def snapshot(self) -> Dict[str, Any]:
        """Everything the cognitive layer might want before planning:
        active app/cwd/recent tool calls (core.context), plus which
        Phase 17.1 plugins are loaded - cheap, side-effect free."""
        snap = self._conversation.snapshot()
        snap["loaded_plugins"] = [p.name for p in self._phase16.plugins]
        return snap

    def record_tool_result(self, tool_name: str, arguments: Dict, result: Dict) -> None:
        self._conversation.record_tool_result(tool_name, arguments, result)
        self.emit_stage("step", tool=tool_name, success=isinstance(result, dict) and not result.get("error"))

    # -- memory --------------------------------------------------------------
    def remember_outcome(self, goal: str, outcome_summary: str, satisfied: bool) -> Dict:
        """Files a completed (or abandoned) goal into long-term + vector
        memory so a future recall_related() on a similar goal can see
        what happened last time, instead of the cognitive layer starting
        from zero on every run."""
        key = f"goal_outcome:{abs(hash(goal)) % 10**8}"
        value = f"Goal: {goal}\nSatisfied: {satisfied}\nSummary: {outcome_summary}"
        return self._memory.remember(key, value, category="cognition")

    def recall_related(self, goal: str, top_k: int = 3) -> Dict:
        """Similar past goals/outcomes, if any - purely advisory, never
        blocks planning if memory backends aren't configured."""
        try:
            return self._memory.recall_similar(goal, top_k=top_k)
        except Exception as e:
            return {"error": str(e), "results": []}

    # -- observability --------------------------------------------------------
    def emit_stage(self, stage: str, **payload) -> None:
        """Emits "cognition:<stage>" on the Phase 17.1 unified bus. Never
        raises - a missing/broken subscriber must never interrupt the
        actual goal execution."""
        try:
            self._phase16.events.emit(f"cognition:{stage}", **payload)
        except Exception:
            from core.error_trace import log_swallowed as _lsw

            _lsw("cognitive_core.context_bridge.emit_stage")

    @property
    def phase16(self):
        """Escape hatch to the full Phase 17.1 bridge (brain/events/config/plugins)."""
        return self._phase16


def get_context_bridge() -> CognitiveContextBridge:
    global _context_bridge
    with _lock:
        if _context_bridge is None:
            _context_bridge = CognitiveContextBridge()
        return _context_bridge
