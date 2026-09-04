"""Wellness goal manager
========================
User-set daily/weekly targets per metric, checked against
activity_tracker.py's actuals. Same JSON-state persistence pattern as
finance/budget_manager.py - deliberately mirrored for consistency.

Every target is a number the user chooses; this module never invents,
suggests, or defaults a target on its own - there is no built-in "you
should walk 10,000 steps" assumption anywhere here.
"""

import json
from pathlib import Path
from typing import Dict, Optional

from core.logger import get_logger
from wellness.activity_tracker import get_activity_tracker

logger = get_logger("ultron.wellness.goals")

DATA_PATH = Path(__file__).resolve().parents[1] / "storage" / "wellness" / "goals.json"

# metric -> which daily_summary() field it's compared against, and
# whether "higher is better" (steps/water/sleep/workouts) - all of
# today's supported metrics are, so this is just documentation of that
# assumption rather than a per-metric switch.
_METRIC_FIELDS = {
    "steps": "steps",
    "water_ml": "water_ml",
    "sleep_hours": "sleep_hours",
    "workouts_weekly": None,  # weekly metric, handled separately below
}


class GoalManager:
    def __init__(self):
        self._goals: Dict[str, float] = self._load()

    def _load(self) -> Dict[str, float]:
        try:
            if DATA_PATH.exists():
                return json.loads(DATA_PATH.read_text(encoding="utf-8"))
        except Exception:
            logger.exception("goal_manager: state load failed, starting fresh")
        return {}

    def _save(self) -> None:
        try:
            DATA_PATH.parent.mkdir(parents=True, exist_ok=True)
            DATA_PATH.write_text(json.dumps(self._goals, indent=2), encoding="utf-8")
        except Exception:
            logger.exception("goal_manager: state save failed")

    def set_goal(self, metric: str, target: float) -> Dict:
        metric = (metric or "").strip().lower()
        if metric not in _METRIC_FIELDS:
            return {"success": False, "error": f"unknown metric '{metric}'. Valid: {sorted(_METRIC_FIELDS)}"}
        try:
            target = float(target)
        except (TypeError, ValueError):
            return {"success": False, "error": f"invalid target: {target!r}"}
        if target <= 0:
            return {"success": False, "error": "target must be positive"}

        self._goals[metric] = target
        self._save()
        return {"success": True, "metric": metric, "target": target}

    def remove_goal(self, metric: str) -> Dict:
        metric = (metric or "").strip().lower()
        removed = self._goals.pop(metric, None) is not None
        if removed:
            self._save()
        return {"success": removed}

    def get_status(self) -> Dict:
        """Compares today's actuals (and this week's workout count) against
        every set goal. Metrics with no goal set are omitted."""
        tracker = get_activity_tracker()
        today = tracker.daily_summary()
        week = tracker.weekly_summary()

        rows = []
        for metric, target in self._goals.items():
            if metric == "workouts_weekly":
                actual = week["total_workouts"]
            else:
                actual = today.get(_METRIC_FIELDS[metric], 0)

            ratio = (actual / target) if target else 0.0
            rows.append(
                {
                    "metric": metric,
                    "target": target,
                    "actual": actual,
                    "percent_of_goal": round(ratio * 100, 1),
                    "met": ratio >= 1.0,
                }
            )

        return {
            "success": True,
            "goals": rows,
            "goals_met": sum(1 for r in rows if r["met"]),
            "goals_total": len(rows),
        }


_goal_manager: Optional[GoalManager] = None


def get_goal_manager() -> GoalManager:
    global _goal_manager
    if _goal_manager is None:
        _goal_manager = GoalManager()
    return _goal_manager
