"""
Learner (Phase 4.1 - Learning & Safety)
========================================
Turns learning/experience.py's raw log into an answer to one question:
"based on everything Ultron has actually seen happen, how much should
it trust doing `action_name` again?" safety/trust_policy.py is the only
normal caller of the read side (get_confidence / recommend); this module
owns the write side too so the two stay consistent.

Learning is passive by default, same pattern as proactive/predictor.py:
__init__ subscribes to core.event_bus's "action.completed" and
"action.failed" events, so every action that goes through
core/action_pipeline.py is turned into an Experience without any caller
needing to remember to report it. observe() stays public for manual/
explicit feedback (e.g. a user saying "that was wrong" after the fact,
or safety/sandbox.py reporting a dry-run result).

This module never decides whether an action is *allowed* to run or be
learned from - that's safety/learning_policy.py's job, checked on every
observe(). Actions the policy excludes are still logged for visibility
but are not folded into get_confidence()'s numbers, so an explicitly
untrusted action can't quietly re-earn trust through its side door.
"""

import threading
from typing import Dict, List, Optional

from core.logger import get_logger
from learning.experience import get_experience_store

logger = get_logger("ultron.learning.learner")

# below this many observations, get_confidence() reports None (not "0.5
# neutral") - a handful of coincidences shouldn't look like a settled
# trend to safety/trust_policy.py
MIN_SAMPLES_FOR_CONFIDENCE = 5


class Learner:
    def __init__(self, auto_subscribe: bool = True):
        self._store = get_experience_store()
        self._lock = threading.Lock()
        self._subscribed = False
        if auto_subscribe:
            self._subscribe()

    # -- passive collection ---------------------------------------------------
    def _subscribe(self) -> None:
        try:
            from core.event_bus import get_event_bus

            bus = get_event_bus()
            bus.subscribe("action.completed", self._on_action_completed)
            bus.subscribe("action.failed", self._on_action_failed)
            self._subscribed = True
        except Exception as exc:
            # core.event_bus not available yet (e.g. import order during
            # early startup) - degrade to manual-only mode instead of
            # crashing whatever imported this module
            logger.warning(f"Learner could not subscribe to event_bus: {exc}")

    def _on_action_completed(self, **payload) -> None:
        action = payload.get("action") or payload.get("action_name")
        if not action:
            return
        self.observe(
            action, success=bool(payload.get("success", True)), context=payload.get("context"), source="event_bus"
        )

    def _on_action_failed(self, **payload) -> None:
        action = payload.get("action") or payload.get("action_name")
        if not action:
            return
        self.observe(
            action, success=False, context=payload.get("context"), error=payload.get("error"), source="event_bus"
        )

    # -- write side -------------------------------------------------------
    def observe(
        self,
        action_name: str,
        success: bool,
        context: Optional[Dict] = None,
        reward: Optional[float] = None,
        error: Optional[str] = None,
        source: str = "manual",
    ) -> None:
        """Record one observed outcome. Always logged for audit purposes;
        whether it's allowed to move get_confidence()'s numbers is
        safety/learning_policy.py's call, not this method's."""
        from safety.learning_policy import get_learning_policy

        policy = get_learning_policy()

        learnable = policy.is_action_learnable(action_name)
        self._store.add_experience(
            action_name,
            success,
            context=context,
            reward=reward,
            error=error,
            source=source if learnable else f"{source}:excluded",
        )
        if not learnable:
            logger.info(f"Observed '{action_name}' but learning_policy excludes it - logged only")

    def learn_from_feedback(self, action_name: str, was_good: bool, note: Optional[str] = None) -> None:
        """Explicit human-in-the-loop correction, e.g. 'undo that' or a
        thumbs-down after the fact. Weighted as a full observation -
        direct feedback is the strongest signal this module gets."""
        self.observe(
            action_name,
            success=was_good,
            context={"note": note} if note else None,
            reward=1.0 if was_good else -1.0,
            source="feedback",
        )

    # -- read side --------------------------------------------------------
    def get_confidence(self, action_name: str) -> Optional[float]:
        """0.0-1.0 blended success rate + reward, or None if there
        isn't enough history yet to say anything meaningful."""
        stats = self._store.stats_for(action_name)
        if stats["sample_size"] < MIN_SAMPLES_FOR_CONFIDENCE:
            return None
        # success_rate is already 0..1; avg_reward is -1..1, rescale to
        # 0..1 and blend evenly so one bad-but-technically-successful
        # run (negative explicit reward) still pulls confidence down
        reward_component = (stats["avg_reward"] + 1.0) / 2.0
        return round((stats["success_rate"] + reward_component) / 2.0, 3)

    def get_stats(self, action_name: str) -> Dict:
        return self._store.stats_for(action_name)

    def known_actions(self) -> List[str]:
        return self._store.all_known_actions()

    def summary(self, limit: int = 20) -> List[Dict]:
        """Confidence table for every action with enough history -
        useful for a dashboard/debug view over what Ultron has learned."""
        out = []
        for action in self.known_actions():
            stats = self.get_stats(action)
            out.append({**stats, "confidence": self.get_confidence(action)})
        out.sort(key=lambda r: r["sample_size"], reverse=True)
        return out[:limit]


_learner: Optional[Learner] = None
_learner_lock = threading.Lock()


def get_learner() -> Learner:
    """Process-wide singleton, same pattern as proactive.predictor.get_action_predictor()."""
    global _learner
    with _learner_lock:
        if _learner is None:
            _learner = Learner()
        return _learner
