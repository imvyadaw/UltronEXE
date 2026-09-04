"""
Priority Manager (Phase 30 - Planning)
=========================================
intelligence/goal_manager/goal_store.py stores steps in creation
order and progress_tracker.py advances them in that same order -
neither has a concept of *priority*, so two active goals' steps
always interleave FIFO regardless of urgency. This module sits in
front of goal_store reads and re-orders what core/orchestrator.py
should work on next.

Priority score is deliberately simple (weighted sum, not ML) so it's
auditable - three inputs:
    urgency   - caller-supplied 0-1 (e.g. from
                intelligence/proactive_intelligence/urgency_calculator.py
                if the goal came from a proactive suggestion)
    age       - older pending items drift upward so nothing starves
    retries   - a step that's failed before is deprioritized below
                fresh ones, so one stuck step doesn't block a queue
                of otherwise-healthy work (replanner.py handles
                actually fixing it)
"""

import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class PriorityItem:
    item_id: str
    payload: Dict
    urgency: float = 0.5
    created_at: float = field(default_factory=time.time)
    retry_count: int = 0

    def score(self, now: Optional[float] = None) -> float:
        now = now or time.time()
        age_minutes = (now - self.created_at) / 60.0
        age_boost = min(age_minutes / 30.0, 1.0) * 0.3  # caps out after 30 min
        retry_penalty = min(self.retry_count * 0.15, 0.6)
        return (self.urgency * 0.7) + age_boost - retry_penalty


class PriorityManager:
    def __init__(self):
        self._items: Dict[str, PriorityItem] = {}

    def add(self, item_id: str, payload: Dict, urgency: float = 0.5) -> None:
        self._items[item_id] = PriorityItem(item_id=item_id, payload=payload, urgency=urgency)

    def mark_retry(self, item_id: str) -> None:
        if item_id in self._items:
            self._items[item_id].retry_count += 1

    def remove(self, item_id: str) -> None:
        self._items.pop(item_id, None)

    def next(self) -> Optional[PriorityItem]:
        """Highest-scoring item still pending, or None if empty."""
        if not self._items:
            return None
        now = time.time()
        return max(self._items.values(), key=lambda it: it.score(now))

    def ordered(self) -> List[PriorityItem]:
        now = time.time()
        return sorted(self._items.values(), key=lambda it: it.score(now), reverse=True)


_instance: Optional[PriorityManager] = None


def get_priority_manager() -> PriorityManager:
    """Singleton is fine here (unlike stop_conditions.py) - priority
    ordering is meant to span every active goal at once, not reset
    per-run."""
    global _instance
    if _instance is None:
        _instance = PriorityManager()
    return _instance
