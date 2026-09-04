"""
LEARN (Phase 18.9.1)
=========================
Feedback loops over what Ultron has done, as opposed to PREDICT/'s
forward-looking pattern matching:

    from_mistake.py   - corrected-pairs log (context -> correction),
                        with difflib fuzzy lookup so a near-repeat of
                        a past mistake still surfaces its correction.
    from_habit.py     - recurring action-subsequence detection over a
                        rolling log (distinct from PREDICT/
                        next_action.py's single-step transitions).
    from_feedback.py  - per-item like/dislike rating aggregation.
    improve_self.py   - one consolidated report across the three
                        modules above, plus low_rated_items() and
                        check_for_repeat_mistake() convenience
                        lookups.

All local state (mistake log, action log, ratings) lives under
data/ai_evolution/ by default, each path overridable via its own
AI_EVOLUTION_*_ENV variable. No third-party dependencies - every
module here is stdlib-only (difflib for fuzzy matching, collections
for counting), so there's nothing to import-guard in this package.

Purely additive - nothing in Phase 1-18.9 imports from here. This
package doesn't apply any correction or adjust any weight on its own;
every module here only stores and reports, leaving the decision of
what to actually do with a suggestion to whichever caller asks for
one.
"""

from learn.from_mistake import get_from_mistake
from learn.from_habit import get_from_habit
from learn.from_feedback import get_from_feedback
from learn.improve_self import get_improve_self

__all__ = [
    "get_from_mistake",
    "get_from_habit",
    "get_from_feedback",
    "get_improve_self",
]
