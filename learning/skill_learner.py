"""Skill learner
=============
Two things already turn Ultron's own activity into reusable
step-sequences, and neither covers this module's job:

    - intelligence/skill_builder/workflow_detector.py mines the ambient
      raw action-name stream for n-grams that repeat *unprompted*, with
      no notion of whether any single run of them actually succeeded.
    - learning/pattern_detector.py mines memory/episodic/'s bounded,
      outcome-scored episodes, but only promotes a step-sequence to
      memory/procedural/ once it has recurred MIN_SEQUENCE_OCCURRENCES
      times - by design, a one-off success is never enough on its own.

Both are the right call for *automatic* detection, but neither has a
path for "the user (or Ultron's own self-critique) just watched this
succeed once and wants it remembered right now" - explicit intent that
shouldn't have to wait for accidental repetition. learn_from_episode()
is that path: it takes one already-successful memory/episodic/ episode
and saves/updates it directly as a memory/procedural/ procedure *and*
an intelligence/skill_builder/ skill record, skipping the recurrence
threshold entirely.

assess_mastery() is the other half: a saved procedure's raw
success_rate (memory/procedural/) doesn't distinguish "used twice,
both fine" from "used twenty times, reliable" - this grades that into
novice / competent / mastered using both success_rate and uses, and
promote_masters() syncs anything mastered into skill_builder's
STATUS_ACTIVE so the rest of the skill-builder pipeline (which already
promotes/deprecates its own detected skills via skill_improver.py)
treats an explicitly-taught skill exactly as trustworthy as one it
found by itself.

Phase 4.5: promote_masters() used to flip STATUS_ACTIVE unconditionally
the moment a procedure crossed the mastery thresholds - full autonomy
over what starts running unattended, regardless of what the procedure
actually does. It now runs safety/policy.py's classify() first; a
procedure that trips a risk keyword (destructive/financial/outbound-
communication/system-security - see that module) is queued in
safety/review_queue.py instead of promoted, and only reaches
STATUS_ACTIVE once a human calls review_queue.approve() and a later
promote_masters() call picks it up via apply_approved_promotions().
Nothing here changes how mastery itself is graded.
"""

from typing import Dict, List, Optional

from core.logger import get_logger
from memory.episodic import get_episodic_memory
from memory.procedural import get_procedural_outcome_memory
from intelligence.skill_builder import get_skill_store
from intelligence.skill_builder.skill_store import STATUS_ACTIVE
from safety.policy import get_safety_policy, TIER_REVIEW
from safety.review_queue import get_review_queue

logger = get_logger("skill_learner")

MASTERY_COMPETENT_MIN_USES = 3
MASTERY_COMPETENT_MIN_RATE = 0.6
MASTERY_MASTERED_MIN_USES = 8
MASTERY_MASTERED_MIN_RATE = 0.85


class SkillLearner:
    """Explicit skill acquisition from a single successful episode, plus mastery grading."""

    def __init__(self):
        self.episodic = get_episodic_memory()
        self.procedural = get_procedural_outcome_memory()
        self.skill_store = get_skill_store()
        self.safety_policy = get_safety_policy()
        self.review_queue = get_review_queue()

    def learn_from_episode(self, episode_id: int, name: Optional[str] = None, goal_keywords: str = "") -> Dict:
        """Save a successful episode's steps directly as a named
        procedure + skill, bypassing pattern_detector's recurrence
        threshold. Only works on an episode that already ended in
        success - teaching Ultron a failure as a "skill" would defeat
        the point."""
        try:
            episode = self.episodic.get_episode(episode_id)
            if "error" in episode:
                return episode
            if not episode["success"]:
                return {"error": f"Episode {episode_id} did not end in success - nothing to learn"}
            if not episode["steps"]:
                return {"error": f"Episode {episode_id} has no recorded steps to learn from"}

            steps = [{"tool": s["description"], "arguments": s["detail"]} for s in episode["steps"]]
            name = name or f"{episode['kind']}_{episode_id}"
            keywords = goal_keywords or episode["kind"]

            proc_result = self.procedural.save_procedure(
                name, steps, description=episode["goal"], goal_keywords=keywords
            )
            if "error" in proc_result:
                return proc_result
            self.procedural.record_outcome(name, success=True)

            skill_row = self.skill_store.find_by_name(name)
            if skill_row is None:
                skill_id = self.skill_store.save_skill(
                    {
                        "name": name,
                        "description": episode["goal"],
                        "steps": steps,
                        "source": f"skill_learner:episode_{episode_id}",
                    }
                )
            else:
                skill_id = skill_row["skill_id"]
                self.skill_store.update_steps(skill_id, steps)
            self.skill_store.record_usage(skill_id, success=True)

            logger.info(f"Learned skill '{name}' from episode {episode_id}")
            return {"success": True, "name": name, "skill_id": skill_id, "step_count": len(steps)}
        except Exception as e:
            logger.error(f"learn_from_episode() failed: {e}")
            return {"error": str(e)}

    def assess_mastery(self, name: str) -> Dict:
        """Grade a saved procedure's mastery level from its
        memory/procedural/ track record. novice: fewer than
        MASTERY_COMPETENT_MIN_USES uses, or a low success rate.
        competent: enough uses with a decent success rate. mastered:
        heavily used with a high success rate."""
        try:
            proc = self.procedural.get_procedure(name)
            if "error" in proc:
                return proc
            uses = proc["success_count"] + proc["failure_count"]
            rate = proc["success_rate"]
            if rate is not None and uses >= MASTERY_MASTERED_MIN_USES and rate >= MASTERY_MASTERED_MIN_RATE:
                level = "mastered"
            elif rate is not None and uses >= MASTERY_COMPETENT_MIN_USES and rate >= MASTERY_COMPETENT_MIN_RATE:
                level = "competent"
            else:
                level = "novice"
            return {"name": name, "mastery": level, "uses": uses, "success_rate": rate}
        except Exception as e:
            logger.error(f"assess_mastery() failed: {e}")
            return {"error": str(e)}

    def promote_masters(self) -> Dict:
        """Scan every saved procedure; anything graded 'mastered' gets
        its matching skill_store row (if any) set to STATUS_ACTIVE, so
        the skill_builder pipeline trusts it the same as a skill it
        detected and proved out itself - unless safety/policy.py
        classifies it TIER_REVIEW, in which case it's queued in
        safety/review_queue.py instead of promoted (see this module's
        docstring). Also applies any promotions a human has since
        approved from a previous cycle's queue entries."""
        try:
            procedures = self.procedural.list_procedures()
            if "error" in procedures:
                return procedures
            promoted: List[str] = []
            queued: List[str] = []
            for proc in procedures["procedures"]:
                assessment = self.assess_mastery(proc["name"])
                if assessment.get("mastery") != "mastered":
                    continue
                skill_row = self.skill_store.find_by_name(proc["name"])
                if not skill_row or skill_row["status"] == STATUS_ACTIVE:
                    continue
                classification = self.safety_policy.classify(proc["name"], steps=proc.get("steps"))
                if classification["tier"] == TIER_REVIEW:
                    self.review_queue.request_approval(
                        name=proc["name"],
                        kind="skill_promotion",
                        reason=classification["reason"],
                        matched=classification["matched"],
                        payload={"skill_id": skill_row["skill_id"]},
                    )
                    queued.append(proc["name"])
                    continue
                self.skill_store.set_status(skill_row["skill_id"], STATUS_ACTIVE)
                promoted.append(proc["name"])
            applied = self.apply_approved_promotions()
            return {
                "promoted": promoted,
                "count": len(promoted),
                "queued_for_review": queued,
                "applied_from_review": applied,
            }
        except Exception as e:
            logger.error(f"promote_masters() failed: {e}")
            return {"error": str(e)}

    def apply_approved_promotions(self) -> List[str]:
        """Pick up any 'skill_promotion' review items a human has
        approved since the last cycle and actually flip them to
        STATUS_ACTIVE now - kept separate from the approve() call
        itself (safety/review_queue.py) so a human can approve from
        wherever they review the queue without that surface needing to
        know anything about skill_store."""
        applied: List[str] = []
        try:
            result = self.review_queue.approved_unapplied(kind="skill_promotion")
            for item in result.get("items", []):
                skill_id = item.get("payload", {}).get("skill_id")
                if skill_id is not None:
                    self.skill_store.set_status(skill_id, STATUS_ACTIVE)
                    applied.append(item["name"])
                    logger.info(f"Applied reviewer-approved promotion: '{item['name']}'")
                self.review_queue.mark_applied(item["id"])
        except Exception as e:
            logger.error(f"apply_approved_promotions() failed: {e}")
        return applied


_skill_learner: Optional[SkillLearner] = None


def get_skill_learner() -> SkillLearner:
    global _skill_learner
    if _skill_learner is None:
        _skill_learner = SkillLearner()
    return _skill_learner
