"""
Consciousness (Phase 21 - Unified Core Architecture)
=====================================================
Same naming caveat as PHASE_18_1_CORE_FOUNDATION/CORE/consciousness.py,
which this module supersedes as the process-wide instance from Phase 21
on (that file is left in place for its own phase folder's demo/tests;
new code should `from core.consciousness import get_consciousness`, not
reach into PHASE_18_1_CORE_FOUNDATION). This is bookkeeping, not a
sentience claim: one place that answers "what is Ultron doing right
now, how sure is it, and what got interrupted".

What's new versus the Phase 18.1 version: reflect() now also reports
the active goal (core.goal_manager) and how many capabilities are
registered/enabled (core.capability_registry), both best-effort so a
missing subsystem just omits that field. push_focus()/pop_focus() also
emit on core.event_bus so a debug console or ui/tray can show live
attention changes instead of polling reflect().

Read-only with respect to everything it reports on - starting, stopping,
or retrying a task is action_pipeline/autonomous_engine's job; this
module only watches and remembers.
"""

import time
from collections import deque
from typing import Deque, Dict, List, Optional

MAX_INTROSPECTION_LOG = 100
CONFIDENCE_WINDOW = 20
DEFAULT_CONFIDENCE = 0.5  # no data yet - neither confident nor worried


class ConsciousnessState:
    """Process-wide introspective state. Use get_consciousness()."""

    def __init__(self):
        self._focus_stack: List[Dict] = []
        self._introspection_log: Deque[Dict] = deque(maxlen=MAX_INTROSPECTION_LOG)
        self._recent_outcomes: Deque[bool] = deque(maxlen=CONFIDENCE_WINDOW)

    # -- focus / attention -----------------------------------------------
    def push_focus(self, description: str, source: str = "goal") -> None:
        self._focus_stack.append({"description": description, "source": source, "started_at": time.time()})
        self._note(f"focus started: {description}", meta={"source": source})
        self._emit("consciousness.focus_started", description=description, source=source)

    def pop_focus(self) -> Optional[Dict]:
        if not self._focus_stack:
            return None
        entry = self._focus_stack.pop()
        entry["duration_seconds"] = round(time.time() - entry["started_at"], 1)
        self._note(f"focus ended: {entry['description']}", meta={"duration_seconds": entry["duration_seconds"]})
        self._emit(
            "consciousness.focus_ended", description=entry["description"], duration_seconds=entry["duration_seconds"]
        )
        return entry

    @property
    def current_focus(self) -> Optional[str]:
        return self._focus_stack[-1]["description"] if self._focus_stack else None

    @property
    def attention_depth(self) -> int:
        return len(self._focus_stack)

    # -- confidence ----------------------------------------------------
    def note_outcome(self, satisfied: bool, detail: str = "") -> None:
        self._recent_outcomes.append(bool(satisfied))
        if not satisfied:
            self._note(f"setback: {detail or 'attempt not satisfied'}")

    @property
    def confidence(self) -> float:
        if not self._recent_outcomes:
            return DEFAULT_CONFIDENCE
        return round(sum(self._recent_outcomes) / len(self._recent_outcomes), 2)

    # -- introspection log ---------------------------------------------
    def _note(self, event: str, meta: Optional[Dict] = None) -> None:
        self._introspection_log.append({"event": event, "meta": meta or {}, "timestamp": time.time()})

    def _emit(self, event_name: str, **payload) -> None:
        try:
            from core.event_bus import get_event_bus

            get_event_bus().emit(event_name, **payload)
        except Exception:
            from core.error_trace import log_swallowed as _lsw

            _lsw("core.consciousness._emit")

    def recent_notes(self, limit: int = 10) -> List[Dict]:
        return list(self._introspection_log)[-limit:]

    # -- rollup ----------------------------------------------------------
    def reflect(self) -> Dict:
        """One honest snapshot of current state, best-effort enriched
        with the active goal and capability counts."""
        active_tasks = None
        try:
            from core.task_queue import get_task_queue

            active_tasks = len(get_task_queue().list_tasks(status="running").get("tasks", []))
        except Exception:
            from core.error_trace import log_swallowed as _lsw

            _lsw("core.consciousness.reflect")

        active_goal = None
        try:
            from core.goal_manager import get_goal_manager

            goal = get_goal_manager().active_goal()
            active_goal = goal.get("title") if goal else None
        except Exception:
            from core.error_trace import log_swallowed as _lsw

            _lsw("core.consciousness.reflect")

        capability_count = None
        try:
            from core.capability_registry import get_capability_registry

            capability_count = len(get_capability_registry().list_by_category())
        except Exception:
            from core.error_trace import log_swallowed as _lsw

            _lsw("core.consciousness.reflect")

        recent_setbacks = sum(1 for o in self._recent_outcomes if not o)

        return {
            "focus": self.current_focus,
            "attention_depth": self.attention_depth,
            "confidence": self.confidence,
            "recent_setbacks": recent_setbacks,
            "outcomes_tracked": len(self._recent_outcomes),
            "active_background_tasks": active_tasks,
            "active_goal": active_goal,
            "registered_capabilities": capability_count,
            "recent_notes": self.recent_notes(5),
        }


_state: Optional[ConsciousnessState] = None


def get_consciousness() -> ConsciousnessState:
    global _state
    if _state is None:
        _state = ConsciousnessState()
    return _state
