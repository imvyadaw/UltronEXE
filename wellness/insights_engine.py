"""Wellness insights engine
============================
Combines activity_tracker + goal_manager + streak_tracker into one
report, with an optional AI-narrated summary - same fail-closed
"narrate if possible, otherwise raw numbers" pattern as
finance/insights_engine.py.

The narration prompt is deliberately restricted to progress-against-
self-set-goals framing (steps/water/sleep/workouts/mood trend) - no
nutrition, no weight, no body commentary, and no diagnostic language.
"""

from typing import Dict, Optional

from core.logger import get_logger
from wellness.activity_tracker import get_activity_tracker
from wellness.goal_manager import get_goal_manager
from wellness.streak_tracker import get_streak_tracker

logger = get_logger("ultron.wellness.insights")


class WellnessInsightsEngine:
    def generate_report(self, narrate: bool = True) -> Dict:
        today = get_activity_tracker().daily_summary()
        week = get_activity_tracker().weekly_summary()
        goals = get_goal_manager().get_status()
        streaks = get_streak_tracker().get_streaks()

        report: Dict = {
            "success": True,
            "today": today,
            "week": week,
            "goals": goals,
            "streaks": streaks,
        }

        if narrate:
            narration = self._narrate(report)
            if narration:
                report["narration"] = narration

        return report

    def _narrate(self, report: Dict) -> Optional[str]:
        try:
            from ai.ai_router import AIRouter

            router = AIRouter()
            prompt = (
                "Summarize this personal activity snapshot in 3-4 short, encouraging sentences. "
                "Focus only on progress against the goals the user set themselves (steps/water/sleep/"
                "workouts) and any streaks. Do not comment on weight, diet, calories, or body image, "
                "and do not give medical advice. Data:\n"
                f"today={report['today']}\nweek={report['week']}\ngoals={report['goals']}\nstreaks={report['streaks']}\n"
            )
            text = router.complete(prompt)
            return (text or "").strip() or None
        except Exception:
            logger.info("wellness.insights_engine: narration unavailable (no ai_router or call failed), returning raw numbers only")
            return None


_wellness_insights_engine: Optional[WellnessInsightsEngine] = None


def get_wellness_insights_engine() -> WellnessInsightsEngine:
    global _wellness_insights_engine
    if _wellness_insights_engine is None:
        _wellness_insights_engine = WellnessInsightsEngine()
    return _wellness_insights_engine
