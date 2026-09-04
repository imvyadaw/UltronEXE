"""
Improve Self (LEARN)
========================
The read-and-summarize side of this package, mirroring
PHASE_18_9_SMART_DEVICES's sync_all.py: one call that fans out across
from_mistake.py, from_habit.py and from_feedback.py and comes back
with a single report, rather than a caller pulling all three
separately. run_improvement_pass() is read-only itself - it doesn't
change any weights or behavior - the point is to hand a caller (a
scheduled job, a "how am I doing" voice query, a dashboard) one
consolidated view of what's been learned so it can decide what to act
on.

low_rated_items() is the one piece of actual judgment this module
adds: items from from_feedback.py whose average score is at or below
a caller-supplied threshold, surfaced together since "what's
underperforming" is a different question from "what's the raw data"
and worth a dedicated helper rather than making every caller
replicate the same filter.
"""

from typing import Dict, List, Optional

from learn.from_mistake import get_from_mistake
from learn.from_habit import get_from_habit
from learn.from_feedback import get_from_feedback


class ImproveSelf:
    """Cross-module learning summary. Use get_improve_self()."""

    def run_improvement_pass(self, habit_sequence_length: int = 2) -> Dict:
        """One consolidated pull across all three LEARN modules.
        Returns {"mistakes_logged": int, "recent_mistakes":
        List[dict], "habits": List[dict], "feedback_items": int,
        "error": Optional[str]}. "recent_mistakes" is capped to the 5
        most recent entries so this stays a summary, not a full dump -
        call from_mistake.get_all() directly for everything."""
        mistakes = get_from_mistake().get_all()
        habits = get_from_habit().detect_habits(sequence_length=habit_sequence_length)
        feedback_items = get_from_feedback().list_items()

        return {
            "mistakes_logged": len(mistakes),
            "recent_mistakes": mistakes[-5:],
            "habits": habits,
            "feedback_items": len(feedback_items),
            "error": None,
        }

    def low_rated_items(self, threshold: float = 0.0, min_count: int = 1) -> List[Dict]:
        """Every item from from_feedback.py with an average score at
        or below `threshold` and at least `min_count` ratings on
        file, ranked lowest-average first. Items with fewer than
        `min_count` ratings are excluded rather than treated as
        "bad" - one negative rating shouldn't flag an item as
        underperforming. Returns a list of {"item_id": str,
        "average": float, "count": int}."""
        feedback = get_from_feedback()
        flagged = []
        for item_id in feedback.list_items():
            score = feedback.get_score(item_id)
            if score["average"] is not None and score["count"] >= min_count and score["average"] <= threshold:
                flagged.append({"item_id": item_id, "average": score["average"], "count": score["count"]})
        flagged.sort(key=lambda f: f["average"])
        return flagged

    def check_for_repeat_mistake(self, context: str) -> Optional[Dict]:
        """Convenience wrapper over from_mistake.suggest_correction():
        returns just the single best match for `context` (or None if
        nothing clears its similarity threshold), for a caller that
        only wants a yes/no plus the top suggestion rather than a
        ranked list."""
        suggestions = get_from_mistake().suggest_correction(context, top_n=1)
        return suggestions[0] if suggestions else None


_improve_self: Optional[ImproveSelf] = None


def get_improve_self() -> ImproveSelf:
    global _improve_self
    if _improve_self is None:
        _improve_self = ImproveSelf()
    return _improve_self
