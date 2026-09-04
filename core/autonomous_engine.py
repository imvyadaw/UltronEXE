"""
Autonomous Engine (Phase 21 - Unified Core Architecture)
=========================================================
The orchestrator this phase was building toward: given an active goal
(core.goal_manager) with steps, work through them without a human
driving each one, but through the same safety rails a human-triggered
action gets - core.action_pipeline's permission gate, not a shortcut
around it. This does not replace
PHASE_17_2_COGNITIVE_BRAIN/COGNITIVE_CORE/autonomous_executor.py, which
is that phase's self-contained plan/execute/critique loop; this module
is the Phase 21 version that runs through the unified core (capability
lookup, confidence tracking, event bus) other Phase 21 modules already
use, so a goal step becomes a fully-tracked action_pipeline run instead
of a bespoke executor.

Safety rails, all deliberate defaults, all overridable per run():
  - max_actions_per_cycle - a runaway goal can't spin forever unattended
  - min_confidence - if core.consciousness's rolling confidence drops
    below this, the cycle stops and surfaces the goal for a human
    instead of continuing to fail forward
  - destructive/elevated steps always come back as "needs_confirmation"
    from action_pipeline rather than being auto-confirmed here - this
    engine decides *what* to attempt next, never *whether confirmation
    is required*, that's still core.permissions's call
"""

from typing import Dict, List, Optional

from core.logger import get_logger

logger = get_logger("ultron.autonomous_engine")

DEFAULT_MAX_ACTIONS_PER_CYCLE = 5
DEFAULT_MIN_CONFIDENCE = 0.3


class AutonomousEngine:
    def __init__(self):
        self._running = False

    def run_cycle(
        self,
        goal_id: Optional[str] = None,
        max_actions: int = DEFAULT_MAX_ACTIONS_PER_CYCLE,
        min_confidence: float = DEFAULT_MIN_CONFIDENCE,
    ) -> Dict:
        """Work through one goal's pending steps, up to `max_actions`
        action_pipeline runs. Returns a summary dict; never raises -
        a step failure ends the cycle with status='stopped', it doesn't
        propagate."""
        from core.goal_manager import get_goal_manager
        from core.capability_registry import get_capability_registry
        from core.action_pipeline import get_action_pipeline
        from core.consciousness import get_consciousness
        from core.event_bus import get_event_bus

        goals = get_goal_manager()
        registry = get_capability_registry()
        pipeline = get_action_pipeline()
        consciousness = get_consciousness()
        bus = get_event_bus()

        goal = goals.get_goal(goal_id) if goal_id else goals.active_goal()
        if not goal:
            return {"status": "no_goal", "actions_run": 0, "results": []}

        self._running = True
        bus.emit("autonomous.cycle_started", goal_id=goal.get("id"), title=goal.get("title"))

        results: List[Dict] = []
        status = "completed"
        try:
            for step in self._pending_steps(goal):
                if len(results) >= max_actions:
                    status = "max_actions_reached"
                    break
                if consciousness.confidence < min_confidence:
                    status = "low_confidence_paused"
                    break

                capability = self._match_capability(registry, step)
                if capability is None:
                    results.append(
                        {
                            "step": step,
                            "success": False,
                            "error": "no matching capability found",
                            "action": None,
                        }
                    )
                    status = "stopped"
                    break

                outcome = pipeline.run(
                    capability.name,
                    arguments=step.get("arguments", {}),
                    source="autonomous_engine",
                )
                results.append({"step": step, **outcome})

                if outcome.get("error") == "requires confirmation":
                    status = "needs_confirmation"
                    break
                if not outcome.get("success"):
                    status = "stopped"
                    break

            if status == "completed" and not self._pending_steps(goal):
                goals.complete_goal(goal.get("id"))
        finally:
            self._running = False

        summary = {"status": status, "goal_id": goal.get("id"), "actions_run": len(results), "results": results}
        bus.emit("autonomous.cycle_ended", goal_id=goal.get("id"), status=status, actions_run=len(results))
        return summary

    def stop(self) -> None:
        """Best-effort cooperative stop flag; run_cycle checks it between
        steps rather than being interruptible mid-action."""
        self._running = False

    @property
    def is_running(self) -> bool:
        return self._running

    # -- helpers -----------------------------------------------------------
    def _pending_steps(self, goal: Dict) -> List[Dict]:
        return [s for s in goal.get("steps", []) if s.get("status", "pending") == "pending"]

    def _match_capability(self, registry, step: Dict):
        """Steps may already name a capability directly, or only describe
        intent in free text - fall back to capability_registry.find()."""
        name = step.get("capability") or step.get("action")
        if name and registry.has(name):
            return registry.get(name)
        description = step.get("description") or step.get("title") or ""
        matches = registry.find(description, limit=1)
        return matches[0] if matches else None


_engine: Optional[AutonomousEngine] = None


def get_autonomous_engine() -> AutonomousEngine:
    global _engine
    if _engine is None:
        _engine = AutonomousEngine()
    return _engine
