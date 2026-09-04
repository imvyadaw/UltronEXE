"""Failure learner
===============
learn/from_mistake.py and learning_engine/mistake_learner.py already
handle *explicit* mistakes - a human (or Ultron's own self-critique)
says "that was wrong, here's the correction", logged one at a time.
This module handles the failures nobody had to point out by hand,
because the structured outcome data was already being collected:

    - memory/procedural/ tracks success/failure per saved procedure
    - memory/episodic/ tracks success/failure per task episode kind
    - memory/history/tracker.py tracks success/failure per tool call

scan_*() pulls each of those, and anything crossing a failure-rate
threshold gets written down as a `lesson` (a durable, subject-keyed
caution) that should_caution() can check before Ultron leans on that
procedure/kind/tool again. Like mistake_learner.py, this never blocks
anything outright - it only raises a flag with the reason, so a human
or a higher policy layer stays in the loop for the actual decision.

Lessons are stored as flat JSON (storage/learning/failure_lessons.json)
rather than SQLite - a personal assistant accumulates at most a few
hundred of these, and a plain JSON file is easy to inspect/edit by
hand, same trade-off learn/from_mistake.py makes for its own log.
"""

import json
import time
from typing import Dict, Optional

from config import STORAGE_DIR
from core.logger import get_logger
from memory.episodic import get_episodic_memory
from memory.procedural import get_procedural_outcome_memory
from memory.semantic import get_semantic_pattern_memory
from memory.history.tracker import get_interaction_tracker

logger = get_logger("failure_learner")

LESSONS_PATH = STORAGE_DIR / "learning" / "failure_lessons.json"

PROCEDURE_FAILURE_THRESHOLD = 0.4
PROCEDURE_MIN_USES = 3
EPISODE_KIND_FAILURE_THRESHOLD = 0.4
EPISODE_KIND_MIN_ATTEMPTS = 3
TOOL_FAILURE_THRESHOLD = 0.4
TOOL_MIN_USES = 5


class FailureLearner:
    """Aggregates structured success/failure data into caution-worthy lessons."""

    def __init__(self):
        self.procedural = get_procedural_outcome_memory()
        self.episodic = get_episodic_memory()
        self.semantic = get_semantic_pattern_memory()
        self._lessons = self._load()

    def run_scan(self) -> Dict:
        """Run every scan and record any newly-crossed-threshold lessons.
        Safe to call repeatedly - an already-recorded lesson for the same
        subject is refreshed in place, not duplicated."""
        try:
            procedures = self.scan_procedures()
            episodes = self.scan_episodes()
            tools = self.scan_tool_usage()
            return {
                "procedure_lessons": procedures,
                "episode_kind_lessons": episodes,
                "tool_lessons": tools,
                "total_lessons": len(self._lessons),
            }
        except Exception as e:
            logger.error(f"run_scan() failed: {e}")
            return {"error": str(e)}

    # -- scans -------------------------------------------------------------
    def scan_procedures(
        self, threshold: float = PROCEDURE_FAILURE_THRESHOLD, min_uses: int = PROCEDURE_MIN_USES
    ) -> Dict:
        """Flag saved procedures with a poor success rate."""
        try:
            flagged = self.procedural.flag_unreliable(threshold=threshold, min_uses=min_uses)
            if "error" in flagged:
                return flagged
            recorded = []
            for proc in flagged["procedures"]:
                self.record_lesson(
                    subject=proc["name"],
                    subject_type="procedure",
                    lesson=f"succeeds only {proc['success_rate']:.0%} of the time over "
                    f"{proc['success_count'] + proc['failure_count']} attempts",
                    severity="caution",
                    evidence={
                        "success_rate": proc["success_rate"],
                        "uses": proc["success_count"] + proc["failure_count"],
                    },
                )
                recorded.append(proc["name"])
            return {"flagged": recorded, "count": len(recorded)}
        except Exception as e:
            logger.error(f"scan_procedures() failed: {e}")
            return {"error": str(e)}

    def scan_episodes(
        self, threshold: float = EPISODE_KIND_FAILURE_THRESHOLD, min_attempts: int = EPISODE_KIND_MIN_ATTEMPTS
    ) -> Dict:
        """Flag episode `kind`s (task types) with a poor success rate."""
        try:
            rates = self.episodic.failure_rate_by_kind()
            if "error" in rates:
                return rates
            recorded = []
            for kind, stats in rates.items():
                if stats["attempts"] < min_attempts or stats["success_rate"] is None:
                    continue
                if stats["success_rate"] < threshold:
                    self.record_lesson(
                        subject=kind,
                        subject_type="episode_kind",
                        lesson=f"'{kind}' tasks succeed only {stats['success_rate']:.0%} of the time "
                        f"over {stats['attempts']} attempts",
                        severity="caution",
                        evidence=stats,
                    )
                    recorded.append(kind)
            return {"flagged": recorded, "count": len(recorded)}
        except Exception as e:
            logger.error(f"scan_episodes() failed: {e}")
            return {"error": str(e)}

    def scan_tool_usage(self, threshold: float = TOOL_FAILURE_THRESHOLD, min_uses: int = TOOL_MIN_USES) -> Dict:
        """Flag tools/actions logged via memory/history/tracker.py with a
        poor success rate."""
        try:
            stats = get_interaction_tracker().stats_by_name()
            if isinstance(stats, dict) and "error" in stats:
                return stats
            recorded = []
            for name, s in stats.items():
                if s["uses"] < min_uses or s["success_rate"] is None:
                    continue
                if s["success_rate"] < threshold:
                    self.record_lesson(
                        subject=name,
                        subject_type="tool",
                        lesson=f"'{name}' fails {100 - s['success_rate'] * 100:.0f}% of the time "
                        f"over {s['uses']} uses",
                        severity="caution",
                        evidence=s,
                    )
                    recorded.append(name)
            return {"flagged": recorded, "count": len(recorded)}
        except Exception as e:
            logger.error(f"scan_tool_usage() failed: {e}")
            return {"error": str(e)}

    # -- lessons store -------------------------------------------------------
    def record_lesson(
        self, subject: str, subject_type: str, lesson: str, severity: str = "caution", evidence: Optional[Dict] = None
    ) -> Dict:
        """Persist (or refresh) a lesson for `subject`. Also files a
        low-key semantic pattern, so a failure trend shows up alongside
        the regularities learning/pattern_detector.py finds, not just in
        this module's own store."""
        try:
            key = f"{subject_type}:{subject}"
            self._lessons[key] = {
                "subject": subject,
                "subject_type": subject_type,
                "lesson": lesson,
                "severity": severity,
                "evidence": evidence or {},
                "updated_at": time.time(),
            }
            self._save()
            self.semantic.add_pattern(
                pattern_type="failure_lesson",
                description=lesson,
                trigger_condition=f"{subject_type}={subject}",
                typical_outcome="failure",
                confidence=0.6,
            )
            return {"success": True, "subject": subject, "lesson": lesson}
        except Exception as e:
            logger.error(f"record_lesson() failed: {e}")
            return {"error": str(e)}

    def should_caution(self, subject: str, subject_type: Optional[str] = None) -> Dict:
        """Check whether `subject` (a procedure name, episode kind, or
        tool name) has a recorded lesson. Callers should use this as a
        prompt to double-check with the user or pick an alternative -
        never as an automatic block."""
        matches = [
            lesson
            for key, lesson in self._lessons.items()
            if lesson["subject"] == subject and (subject_type is None or lesson["subject_type"] == subject_type)
        ]
        if not matches:
            return {"caution": False, "subject": subject}
        return {"caution": True, "subject": subject, "lessons": matches}

    def check_before_acting(
        self, subject: str, subject_type: Optional[str] = None, context: Optional[str] = None
    ) -> Dict:
        """Combines this module's own structured-data cautions with
        learn/from_mistake.py's explicit corrected-pairs log - the two
        halves of "has Ultron been burned by something like this before".
        should_caution(subject) covers failures nobody had to point out by
        hand (this module's whole reason for existing); suggest_correction
        (context) covers the opposite: a human (or self-critique) already
        corrected a similar context once, on the record. Pass `context` (a
        free-text description of what's about to be attempted, matched
        fuzzily by from_mistake.py) to also check that side; omit it to
        get only the structured-data caution. Never raises - a missing or
        broken from_mistake.py just means that half comes back empty,
        same "advisory, never blocks" stance should_caution() itself
        takes."""
        result = self.should_caution(subject, subject_type=subject_type)
        result["prior_corrections"] = []
        if context:
            try:
                from learn.from_mistake import get_from_mistake

                result["prior_corrections"] = get_from_mistake().suggest_correction(context)
            except Exception:
                from core.error_trace import log_swallowed as _lsw

                _lsw("learning.failure_learner.check_before_acting")
        if result["prior_corrections"] and not result["caution"]:
            result["caution"] = True
        return result

    def all_lessons(self, subject_type: Optional[str] = None) -> Dict:
        lessons = list(self._lessons.values())
        if subject_type:
            lessons = [l for l in lessons if l["subject_type"] == subject_type]
        lessons.sort(key=lambda l: l["updated_at"], reverse=True)
        return {"count": len(lessons), "lessons": lessons}

    def forget_lesson(self, subject: str, subject_type: str) -> Dict:
        key = f"{subject_type}:{subject}"
        if key not in self._lessons:
            return {"error": f"No lesson for {subject_type} '{subject}'"}
        del self._lessons[key]
        self._save()
        return {"success": True, "forgotten": subject}

    # -- persistence ---------------------------------------------------------
    def _load(self) -> Dict:
        if not LESSONS_PATH.exists():
            return {}
        try:
            return json.loads(LESSONS_PATH.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as e:
            logger.warning(f"Could not load failure lessons ({e}), starting fresh")
            return {}

    def _save(self) -> None:
        LESSONS_PATH.parent.mkdir(parents=True, exist_ok=True)
        LESSONS_PATH.write_text(json.dumps(self._lessons, indent=2, ensure_ascii=False), encoding="utf-8")


_failure_learner: Optional[FailureLearner] = None


def get_failure_learner() -> FailureLearner:
    global _failure_learner
    if _failure_learner is None:
        _failure_learner = FailureLearner()
    return _failure_learner
