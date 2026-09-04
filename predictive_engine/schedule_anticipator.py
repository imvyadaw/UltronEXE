"""
schedule_anticipator.py
==========================
Looks for recurring, time-anchored routines in the action history
("every weekday around 9:05am you open VSCode and check email") and
surfaces them as candidate routines the user can confirm, edit, or
dismiss. ULTRON never auto-creates a scheduled task from a detected
pattern without the user opting in - this module only *proposes*.

Dependencies: none beyond the standard library + behavior_modeler.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Tuple

from .behavior_modeler import BehaviorModeler

logger = logging.getLogger("ultron.schedule_anticipator")


@dataclass
class RoutineCandidate:
    action: str
    weekday: int  # 0=Monday ... 6=Sunday
    hour: int
    occurrences: int
    confidence: float
    label: str


_WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


class ScheduleAnticipator:
    """Mines the behavior history for weekday+hour routines."""

    def __init__(self, modeler: BehaviorModeler, min_occurrences: int = 4, min_confidence: float = 0.5):
        self.modeler = modeler
        self.min_occurrences = min_occurrences
        self.min_confidence = min_confidence

    def _bucket_counts(self) -> Dict[Tuple[str, int, int], int]:
        buckets: Dict[Tuple[str, int, int], int] = defaultdict(int)
        for e in self.modeler.history:
            try:
                ts = datetime.fromisoformat(e.timestamp)
            except ValueError:
                continue
            buckets[(e.action, ts.weekday(), ts.hour)] += 1
        return buckets

    def find_routines(self) -> List[RoutineCandidate]:
        buckets = self._bucket_counts()
        # total times this action happened on this weekday (any hour), for confidence normalization
        weekday_totals: Dict[Tuple[str, int], int] = defaultdict(int)
        for (action, weekday, _hour), count in buckets.items():
            weekday_totals[(action, weekday)] += count

        candidates = []
        for (action, weekday, hour), count in buckets.items():
            if count < self.min_occurrences:
                continue
            total_for_weekday = weekday_totals[(action, weekday)]
            confidence = count / total_for_weekday if total_for_weekday else 0
            if confidence < self.min_confidence:
                continue
            label = f"On {_WEEKDAYS[weekday]}s around {hour:02d}:00, you tend to '{action}'"
            candidates.append(RoutineCandidate(action, weekday, hour, count, round(confidence, 2), label))

        candidates.sort(key=lambda c: (c.confidence, c.occurrences), reverse=True)
        return candidates

    def upcoming_today(self, now=None) -> List[RoutineCandidate]:
        """Routines that match today's weekday and are due within the current or next hour."""
        now = now or datetime.now()
        routines = self.find_routines()
        return [r for r in routines if r.weekday == now.weekday() and r.hour in (now.hour, (now.hour + 1) % 24)]


if __name__ == "__main__":
    from pathlib import Path

    logging.basicConfig(level=logging.INFO)
    modeler = BehaviorModeler(store_path=Path("ultron_data/predictive/_demo_behavior_model.json"))
    anticipator = ScheduleAnticipator(modeler, min_occurrences=1, min_confidence=0.0)
    for r in anticipator.find_routines():
        print(r.label, r.confidence)
