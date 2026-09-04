"""
Skill Improver (Phase 19.6 - Skill Builder)
==================================================
Looks at what skill_store.py has recorded about a skill and turns
that into concrete recommendations: promote a reliable "suggested"
skill to "active", deprecate one whose failures have crossed the
line, flag a stale skill nobody's used in a long time, or flag a
duplicate against another skill that covers the same action sequence
with a better track record. review() is advisory-only (just returns
recommendations); apply() carries out the ones safe to make
automatically (promote / deprecate) - merges and stale-cleanup are
left for a human to decide. skill_store.py already applies its own
promote/deprecate rule on every record_usage() call; this module
exists to make that check re-triggerable on demand and to add the
checks skill_store.py can't do on its own (staleness, duplicates).
"""

import threading
import time
from typing import Dict, List, Optional

from intelligence.skill_builder.skill_store import (
    get_skill_store,
    STATUS_ACTIVE,
    STATUS_DEPRECATED,
    STATUS_SUGGESTED,
)

_instance: Optional["SkillImprover"] = None
_instance_lock = threading.Lock()

_STALE_AFTER_SECONDS = 60 * 60 * 24 * 30  # ~30 days untouched with barely any use


class SkillImprover:
    """Turns a skill's recorded stats into promote/deprecate/stale/
    merge_duplicate recommendations."""

    def __init__(self):
        self._store = get_skill_store()

    def review(self, skill_id: int) -> List[Dict]:
        """Advisory only - returns recommendations without changing
        anything."""
        skill = self._store.get_skill(skill_id)
        if skill is None:
            return []

        recommendations = []
        total = skill["success_count"] + skill["failure_count"]

        if skill["status"] == STATUS_SUGGESTED and skill["success_count"] >= 3 and skill["failure_count"] == 0:
            recommendations.append(
                {
                    "type": "promote",
                    "reason": "consistently succeeding while suggested",
                    "detail": f"{skill['success_count']} clean successes",
                }
            )

        if total >= 4 and skill["status"] != STATUS_DEPRECATED and (skill["failure_count"] / total) >= 0.5:
            recommendations.append(
                {
                    "type": "deprecate",
                    "reason": "failure rate too high",
                    "detail": f"{skill['failure_count']}/{total} runs failed",
                }
            )

        if total <= 1 and skill["updated_at"] and (time.time() - skill["updated_at"]) > _STALE_AFTER_SECONDS:
            recommendations.append(
                {
                    "type": "stale",
                    "reason": "barely used and untouched for a long time",
                    "detail": f"only {total} run(s) recorded",
                }
            )

        duplicate = self._find_duplicate(skill)
        if duplicate:
            recommendations.append(
                {
                    "type": "merge_duplicate",
                    "reason": "another skill covers the same steps",
                    "detail": f"skill_id {duplicate['skill_id']} ('{duplicate['name']}') "
                    f"has confidence {duplicate['confidence']:.2f}",
                }
            )

        return recommendations

    def apply(self, skill_id: int) -> Dict:
        """Apply only the recommendations safe to make automatically
        (promote / deprecate). Returns what was applied, alongside the
        full recommendation list for anything left for a human."""
        recommendations = self.review(skill_id)
        applied = []
        for rec in recommendations:
            if rec["type"] == "promote":
                self._store.set_status(skill_id, STATUS_ACTIVE)
                applied.append("promote")
            elif rec["type"] == "deprecate":
                self._store.set_status(skill_id, STATUS_DEPRECATED)
                applied.append("deprecate")
        return {"skill_id": skill_id, "applied": applied, "recommendations": recommendations}

    def _find_duplicate(self, skill: Dict) -> Optional[Dict]:
        sequence = [s.get("action_name") for s in skill.get("steps", [])]
        if not sequence:
            return None
        for other in self._store.list_skills(limit=200):
            if other["skill_id"] == skill["skill_id"]:
                continue
            other_sequence = [s.get("action_name") for s in other.get("steps", [])]
            if other_sequence == sequence and other["confidence"] > skill["confidence"]:
                return other
        return None


def get_skill_improver() -> SkillImprover:
    """Process-wide SkillImprover singleton."""
    global _instance
    if _instance is None:
        with _instance_lock:
            if _instance is None:
                _instance = SkillImprover()
    return _instance
