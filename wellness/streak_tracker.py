"""Streak tracker
=================
Consecutive-day streaks per daily metric (steps/water_ml/sleep_hours),
computed on read from activity_tracker.py's daily_summary() + whatever
target goal_manager.py has set - no separate storage needed, this is a
pure derived view (same "compute, don't duplicate state" choice
budget_manager.py makes against expense_tracker.py).

workouts_weekly is a weekly, not daily, goal - it has no meaningful
"consecutive day" streak, so it's excluded here on purpose.
"""

from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

from wellness.activity_tracker import get_activity_tracker
from wellness.goal_manager import get_goal_manager, _METRIC_FIELDS

MAX_LOOKBACK_DAYS = 90  # cap the walk-back so a metric with no history doesn't scan forever


class StreakTracker:
    def _met_by_offset(self, field: str, target: float) -> List[bool]:
        """Index 0 = today, index 1 = yesterday, etc."""
        tracker = get_activity_tracker()
        today = datetime.now(timezone.utc).astimezone().date()
        results = []
        for i in range(MAX_LOOKBACK_DAYS):
            d = (today - timedelta(days=i)).isoformat()
            actual = tracker.daily_summary(d).get(field, 0)
            results.append(actual >= target)
        return results

    def _daily_streak(self, metric: str, target: float) -> Dict:
        field = _METRIC_FIELDS[metric]
        met = self._met_by_offset(field, target)

        # Current streak: if today isn't met yet (day may still be in
        # progress), that doesn't break an existing streak - start
        # counting from yesterday instead. If today IS met, count it.
        start = 0 if met[0] else 1
        current = 0
        for flag in met[start:]:
            if flag:
                current += 1
            else:
                break

        # Best streak ever seen in the lookback window: longest run of
        # consecutive True values anywhere in the list.
        best = 0
        running = 0
        for flag in met:
            running = running + 1 if flag else 0
            best = max(best, running)

        return {
            "metric": metric,
            "target": target,
            "met_today": met[0],
            "current_streak": current,
            "best_streak": best,
        }

    def get_streaks(self) -> Dict:
        goals = dict(get_goal_manager()._goals)  # read-only snapshot of set targets
        streaks = [
            self._daily_streak(metric, target)
            for metric, target in goals.items()
            if metric in _METRIC_FIELDS and _METRIC_FIELDS[metric] is not None
        ]
        return {"success": True, "streaks": streaks}


_streak_tracker: Optional[StreakTracker] = None


def get_streak_tracker() -> StreakTracker:
    global _streak_tracker
    if _streak_tracker is None:
        _streak_tracker = StreakTracker()
    return _streak_tracker
