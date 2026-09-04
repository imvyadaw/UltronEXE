"""
anomaly_detector.py
======================
Flags behavior that deviates noticeably from the patterns
BehaviorModeler has learned - e.g. an action at a very unusual hour,
an action ULTRON has essentially never seen, or a burst of activity
far above the user's normal rate. This is meant for gentle, useful
flags ("this is unusual for you, want me to double-check?"), not
for surveillance or lockout decisions.

Method: simple frequency-based z-score / rarity checks, no ML
training required, fully explainable.

Dependencies: none beyond the standard library + behavior_modeler.
"""

from __future__ import annotations

import logging
import statistics
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from .behavior_modeler import BehaviorModeler

logger = logging.getLogger("ultron.anomaly_detector")


@dataclass
class AnomalyFlag:
    kind: str  # "novel_action" | "unusual_time" | "activity_burst"
    detail: str
    severity: float  # 0-1, higher = more unusual


class AnomalyDetector:
    """Rarity- and rate-based anomaly checks over the recorded action history."""

    def __init__(self, modeler: BehaviorModeler, burst_window_minutes: int = 5, burst_zscore: float = 2.5):
        self.modeler = modeler
        self.burst_window_minutes = burst_window_minutes
        self.burst_zscore = burst_zscore

    def check_action(
        self, action: str, context: Optional[Dict[str, str]] = None, now: Optional[datetime] = None
    ) -> List[AnomalyFlag]:
        now = now or datetime.now()
        flags: List[AnomalyFlag] = []

        # 1. Never-seen-before action
        total_seen = sum(self.modeler.action_counts.values())
        count = self.modeler.action_counts.get(action, 0)
        if total_seen > 20 and count == 0:
            flags.append(AnomalyFlag("novel_action", f"'{action}' has never been done before", severity=0.6))
        elif total_seen > 20 and count / max(total_seen, 1) < 0.005:
            flags.append(AnomalyFlag("novel_action", f"'{action}' is very rare (seen {count}x)", severity=0.3))

        # 2. Unusual hour for this action
        hours_for_action = [
            datetime.fromisoformat(e.timestamp).hour for e in self.modeler.history if e.action == action
        ]
        if len(hours_for_action) >= 5:
            common_hours = {h for h, c in Counter(hours_for_action).most_common(3)}
            if now.hour not in common_hours:
                flags.append(
                    AnomalyFlag(
                        "unusual_time",
                        f"'{action}' is normally done around {sorted(common_hours)}h, not {now.hour}h",
                        severity=0.25,
                    )
                )

        return flags

    def check_activity_burst(self, now: Optional[datetime] = None) -> Optional[AnomalyFlag]:
        """Compare the current rolling window's action count to the historical average window."""
        now = now or datetime.now()
        window = timedelta(minutes=self.burst_window_minutes)

        by_day_window: Dict[str, int] = defaultdict(int)
        for e in self.modeler.history:
            ts = datetime.fromisoformat(e.timestamp)
            bucket_key = ts.strftime("%Y-%m-%d %H:%M")[:-1]  # coarse per-10-min bucket per day
            by_day_window[bucket_key] += 1

        if len(by_day_window) < 10:
            return None  # not enough history to judge a burst

        counts = list(by_day_window.values())
        mean = statistics.mean(counts)
        stdev = statistics.pstdev(counts) or 1.0

        current_count = sum(
            1 for e in self.modeler.history if now - window <= datetime.fromisoformat(e.timestamp) <= now
        )
        z = (current_count - mean) / stdev
        if z >= self.burst_zscore:
            return AnomalyFlag(
                "activity_burst",
                f"{current_count} actions in the last {self.burst_window_minutes} min "
                f"(usual ~{mean:.1f}, z={z:.1f})",
                severity=min(1.0, z / (self.burst_zscore * 2)),
            )
        return None


if __name__ == "__main__":
    from pathlib import Path

    logging.basicConfig(level=logging.INFO)
    modeler = BehaviorModeler(store_path=Path("ultron_data/predictive/_demo_behavior_model.json"))
    detector = AnomalyDetector(modeler)
    print(detector.check_action("delete_all_files"))
