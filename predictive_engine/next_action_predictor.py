"""
next_action_predictor.py
==========================
Predicts what the user is likely to do next by combining:
  1. BehaviorModeler's first-order transition table (what usually
     follows the last action), and
  2. a simple time-of-day / day-of-week frequency bucket (what the
     user usually does "around now").

Both signals are blended into a single ranked list of candidate
actions with a confidence score in [0, 1]. This is intentionally a
transparent, tunable heuristic rather than a black-box model, so a
caller can always explain *why* a prediction was made.

Dependencies: none beyond the standard library + behavior_modeler.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional

from .behavior_modeler import BehaviorModeler

logger = logging.getLogger("ultron.next_action_predictor")


@dataclass
class Prediction:
    action: str
    confidence: float
    reason: str


class NextActionPredictor:
    """Blends transition-based and time-based signals into ranked predictions."""

    def __init__(self, modeler: BehaviorModeler, transition_weight: float = 0.65, time_weight: float = 0.35):
        self.modeler = modeler
        self.transition_weight = transition_weight
        self.time_weight = time_weight
        # time_bucket[(hour, weekday)][action] = count, built lazily from history
        self._time_bucket: Dict[tuple, Dict[str, int]] = defaultdict(lambda: defaultdict(int))
        self._rebuild_time_buckets()

    def _rebuild_time_buckets(self):
        self._time_bucket.clear()
        for event in self.modeler.history:
            try:
                ts = datetime.fromisoformat(event.timestamp)
            except ValueError:
                continue
            key = (ts.hour, ts.weekday())
            self._time_bucket[key][event.action] += 1

    def _time_scores(self, now: Optional[datetime] = None) -> Dict[str, float]:
        now = now or datetime.now()
        key = (now.hour, now.weekday())
        bucket = self._time_bucket.get(key, {})
        total = sum(bucket.values()) or 1
        return {action: count / total for action, count in bucket.items()}

    def predict(self, top_n: int = 3, now: Optional[datetime] = None) -> List[Prediction]:
        last = self.modeler.last_action()
        transition_scores: Dict[str, float] = {}
        if last:
            for action, _count, ratio in self.modeler.likely_followers(last, top_n=10):
                transition_scores[action] = ratio

        time_scores = self._time_scores(now)

        combined: Dict[str, float] = defaultdict(float)
        reasons: Dict[str, List[str]] = defaultdict(list)
        for action, score in transition_scores.items():
            combined[action] += score * self.transition_weight
            reasons[action].append(f"usually follows '{last}'")
        for action, score in time_scores.items():
            combined[action] += score * self.time_weight
            reasons[action].append("matches this time slot's usual pattern")

        ranked = sorted(combined.items(), key=lambda kv: kv[1], reverse=True)[:top_n]
        return [
            Prediction(action=a, confidence=round(min(score, 1.0), 3), reason=" and ".join(reasons[a]))
            for a, score in ranked
        ]

    def refresh(self):
        """Call after a batch of new events if you want time-buckets recomputed immediately."""
        self._rebuild_time_buckets()


if __name__ == "__main__":
    from pathlib import Path

    logging.basicConfig(level=logging.INFO)
    modeler = BehaviorModeler(store_path=Path("ultron_data/predictive/_demo_behavior_model.json"))
    predictor = NextActionPredictor(modeler)
    for p in predictor.predict():
        print(p)
