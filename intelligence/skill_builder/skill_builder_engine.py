"""
Skill Builder Engine (Phase 19.6 - Skill Builder)
=====================================================
Single entry point for the skill_builder/ package: turn what ULTRON
has actually done - either a deliberate walkthrough or a sequence
that keeps repeating on its own - into a reusable, storable skill,
and (optionally) run one back. Ties together:

    workflow_recorder.py   - logs actions, groups explicit recordings
    workflow_detector.py   - finds sequences repeating in the ambient
                              action history, unprompted
    workflow_analyzer.py   - generalizes one or more instances of a
                              sequence into fixed vs {{placeholder}} params
    skill_generator.py     - builds a name + description + steps skill
                              definition from an analysis
    skill_store.py         - persists skills and tracks their usage stats
    skill_improver.py      - turns usage stats into promote/deprecate calls

Two ways in:
  - explicit: start_recording() -> record_step() (...) ->
    stop_recording_and_build() turns one deliberate walkthrough
    straight into a suggested skill.
  - implicit: detect_from_history() mines the ambient action log for
    sequences that have repeated often enough on their own and turns
    the strongest candidates into suggested skills too.

Execution model mirrors Phase 19.5's self_healing_engine: run_skill()
takes an optional `executor` callable, executor(action_name, params)
-> bool (or it can raise, which counts as failure). With an executor,
this module actually runs the skill's steps and records the outcome.
Without one, it runs in advisory/dry-run mode: it returns the
resolved step plan without acting, so a caller can inspect it first.

Storage: database/learned_skills.db, table builder_runs (this
module's own table; the other six sub-modules each keep their own
tables in the same database file).
"""

import json
import sqlite3
import threading
import time
from pathlib import Path
from typing import Callable, Dict, List, Optional

from core.logger import get_logger
from intelligence.skill_builder.workflow_recorder import get_workflow_recorder
from intelligence.skill_builder.workflow_detector import get_workflow_detector
from intelligence.skill_builder.workflow_analyzer import get_workflow_analyzer
from intelligence.skill_builder.skill_generator import get_skill_generator
from intelligence.skill_builder.skill_store import get_skill_store, STATUS_ACTIVE, STATUS_SUGGESTED
from intelligence.skill_builder.skill_improver import get_skill_improver

logger = get_logger("ultron.skill_builder_engine")

DB_PATH = Path(__file__).resolve().parent.parent.parent / "database" / "learned_skills.db"

_instance: Optional["SkillBuilderEngine"] = None
_instance_lock = threading.Lock()


class SkillBuilderEngine:
    """Orchestrates workflow_recorder / workflow_detector /
    workflow_analyzer / skill_generator / skill_store / skill_improver
    into recording -> skill and detection -> skill pipelines, plus a
    heal()-style run_skill(), and persists every build attempt."""

    def __init__(self, db_path: Path = DB_PATH):
        self._db_path = db_path
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
        self._conn.execute("""CREATE TABLE IF NOT EXISTS builder_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                trigger TEXT,
                outcome TEXT,
                skill_id INTEGER,
                detail TEXT,
                timestamp REAL
            )""")
        self._conn.commit()

        self._recorder = get_workflow_recorder()
        self._detector = get_workflow_detector()
        self._analyzer = get_workflow_analyzer()
        self._generator = get_skill_generator()
        self._store = get_skill_store()
        self._improver = get_skill_improver()

    # ---- explicit recording -------------------------------------------------

    def start_recording(self, name: Optional[str] = None) -> str:
        return self._recorder.start_recording(name)

    def record_step(
        self, action_name: str, params: Optional[Dict] = None, success: bool = True, session_id: Optional[str] = None
    ) -> Dict:
        return self._recorder.record_step(action_name, params=params, success=success, session_id=session_id)

    def stop_recording_and_build(
        self, session_id: str, name: Optional[str] = None, description: Optional[str] = None
    ) -> Dict:
        """Stop the session and, if it has enough steps to generalize,
        turn it straight into a suggested skill."""
        stopped = self._recorder.stop_recording(session_id)
        steps = stopped["steps"]
        analysis = self._analyzer.analyze([steps])

        if not analysis["is_generalizable"]:
            run_id = self._log_run("recording", "no_skill", None, analysis["reason"])
            logger.info(f"recording '{session_id}' produced no skill: {analysis['reason']}")
            return {"outcome": "no_skill", "reason": analysis["reason"], "run_id": run_id}

        skill = self._generator.generate(analysis, name=name, description=description, source="recording")
        skill_id = self._store.save_skill(skill)
        run_id = self._log_run("recording", "skill_created", skill_id, skill["name"])
        logger.info(f"recording '{session_id}' -> skill #{skill_id} ('{skill['name']}')")
        return {
            "outcome": "skill_created",
            "skill_id": skill_id,
            "skill": self._store.get_skill(skill_id),
            "run_id": run_id,
        }

    # ---- taught (explicit, single-episode) -------------------------------------

    def learn_from_taught_episode(self, episode_id: int, name: Optional[str] = None, goal_keywords: str = "") -> Dict:
        """Third way in, alongside explicit recording and implicit
        detection: delegates to learning/skill_learner.py's
        learn_from_episode(), which saves an already-successful
        memory/episodic/ episode straight into memory/procedural/ +
        skill_store.py, bypassing both this engine's own recording flow
        and learning/pattern_detector.py's recurrence threshold - "the
        user (or Ultron's own self-critique) just watched this succeed
        once and wants it remembered right now" (see that module's
        docstring). Logged into this engine's own builder_runs table like
        every other build path, so all three ways a skill gets created
        show up in one history."""
        try:
            from learning.skill_learner import get_skill_learner
        except Exception as e:
            return {"outcome": "unavailable", "error": str(e)}

        result = get_skill_learner().learn_from_episode(episode_id, name=name, goal_keywords=goal_keywords)
        if "error" in result:
            run_id = self._log_run("taught_episode", "no_skill", None, result["error"])
            return {**result, "run_id": run_id}
        run_id = self._log_run("taught_episode", "skill_created", result.get("skill_id"), result.get("name"))
        logger.info(f"taught episode {episode_id} -> skill #{result.get('skill_id')} ('{result.get('name')}')")
        return {**result, "run_id": run_id}

    def run_mastery_promotion(self) -> Dict:
        """Delegates to learning/skill_learner.py's promote_masters(): grade
        every saved memory/procedural/ procedure's mastery and flip
        anything 'mastered' to skill_store.py's STATUS_ACTIVE (subject to
        safety/policy.py's review gate - see that module's docstring).
        Complements skill_improver.py, which promotes/deprecates skills
        this engine detected itself; this is the same trust bar applied to
        skills that were explicitly taught via learn_from_taught_episode()
        instead."""
        try:
            from learning.skill_learner import get_skill_learner
        except Exception as e:
            return {"outcome": "unavailable", "error": str(e)}

        result = get_skill_learner().promote_masters()
        self._log_run(
            "mastery_promotion",
            "ran",
            None,
            json.dumps({k: v for k, v in result.items() if k in ("count", "queued_for_review", "applied_from_review")}),
        )
        return result

    # ---- implicit detection ---------------------------------------------------

    def detect_from_history(
        self,
        history_limit: int = 200,
        min_len: int = 2,
        max_len: int = 6,
        min_occurrences: int = 3,
        max_new_skills: int = 3,
    ) -> List[Dict]:
        """Scan the ambient action history for sequences that keep
        repeating, and turn the strongest, not-already-known
        candidates into suggested skills."""
        steps = self._recorder.get_recent_actions(limit=history_limit)
        self._detector.scan(steps, min_len=min_len, max_len=max_len)
        candidates = self._detector.get_candidates(min_occurrences=min_occurrences, limit=max_new_skills * 3)

        created = []
        for candidate in candidates:
            if len(created) >= max_new_skills:
                break
            action_sequence = candidate["actions"]
            if self._is_self_repeating(action_sequence):
                continue  # e.g. [A,B,C,A,B,C] is just the [A,B,C] cycle counted twice, not a new pattern
            if self._store.find_by_name(self._generator.default_name(action_sequence)):
                continue  # already turned this exact sequence into a skill before

            occurrences = self._gather_occurrences(steps, action_sequence)
            if not occurrences:
                continue
            analysis = self._analyzer.analyze(occurrences)
            if not analysis["is_generalizable"]:
                continue

            skill = self._generator.generate(analysis, source="detected_pattern")
            if self._store.find_by_name(skill["name"]):
                continue
            skill_id = self._store.save_skill(skill)
            self._log_run("detected_pattern", "skill_created", skill_id, skill["name"])
            logger.info(f"detected pattern {action_sequence} -> skill #{skill_id} ('{skill['name']}')")
            created.append(self._store.get_skill(skill_id))

        if not created:
            self._log_run("detected_pattern", "no_new_skills", None, f"{len(candidates)} candidates considered")
        return created

    @staticmethod
    def _is_self_repeating(action_sequence: List[str]) -> bool:
        """True if action_sequence is just some smaller cycle repeated
        end to end (e.g. [A,B,C,A,B,C]) rather than a genuinely
        distinct sequence - workflow_detector.py's n-gram scan will
        surface both the cycle and its multiples, and only the
        smallest one is worth turning into a skill."""
        n = len(action_sequence)
        for period in range(1, n):
            if n % period != 0:
                continue
            unit = action_sequence[:period]
            if unit * (n // period) == action_sequence:
                return True
        return False

    @staticmethod
    def _gather_occurrences(steps: List[Dict], action_sequence: List[str]) -> List[List[Dict]]:
        """Every non-overlapping place action_sequence occurs
        contiguously in steps, as a list of matching step-slices - the
        actual instances workflow_analyzer.py generalizes across."""
        n = len(action_sequence)
        occurrences = []
        i = 0
        while i <= len(steps) - n:
            window = steps[i : i + n]
            if [s["action_name"] for s in window] == action_sequence:
                occurrences.append(window)
                i += n  # non-overlapping
            else:
                i += 1
        return occurrences

    # ---- running a stored skill -------------------------------------------------

    def run_skill(
        self, skill_id: int, executor: Optional[Callable[[str, Dict], bool]] = None, overrides: Optional[Dict] = None
    ) -> Dict:
        """Resolve the skill's {{placeholder}}s against `overrides`
        (matched by placeholder name, falling back to the raw param
        key) and either execute it step by step (executor given) or
        just return the resolved plan (executor omitted, advisory
        mode)."""
        skill = self._store.get_skill(skill_id)
        if skill is None:
            return {"outcome": "not_found", "skill_id": skill_id}

        resolved_steps = self._resolve_steps(skill["steps"], overrides or {})

        if executor is None:
            return {"outcome": "planned", "skill_id": skill_id, "steps": resolved_steps}

        ran = []
        overall_success = True
        for step in resolved_steps:
            try:
                success = bool(executor(step["action_name"], step["params"]))
            except Exception as exc:
                logger.warning(f"skill #{skill_id} step '{step['action_name']}' raised: {exc}")
                success = False
            ran.append({"action_name": step["action_name"], "success": success})
            if not success:
                overall_success = False
                break  # stop at the first failed step rather than plowing on

        self._store.record_usage(skill_id, overall_success)
        self._improver.apply(skill_id)
        outcome = "completed" if overall_success else "failed"
        self._log_run("run_skill", outcome, skill_id, json.dumps(ran))
        logger.info(f"skill #{skill_id} run {outcome} ({len(ran)}/{len(resolved_steps)} steps)")
        return {"outcome": outcome, "skill_id": skill_id, "steps_run": ran}

    @staticmethod
    def _resolve_steps(steps: List[Dict], overrides: Dict) -> List[Dict]:
        resolved = []
        for step in steps:
            params = {}
            for key, value in (step.get("params") or {}).items():
                if isinstance(value, str) and value.startswith("{{") and value.endswith("}}"):
                    placeholder = value[2:-2]
                    params[key] = overrides.get(placeholder, overrides.get(key, value))
                else:
                    params[key] = value
            resolved.append({"action_name": step["action_name"], "params": params})
        return resolved

    # ---- generic outcome reporting (intelligence_bridge/skill_learning_bridge.py) --

    def record_outcome(self, name: str, success: bool, context: Optional[Dict] = None) -> Dict:
        """Log a plain named outcome (a tool/operation name, not
        necessarily a learned_skills skill_id) - what
        intelligence_core.record_provider_call(skill=...) reports back
        after a real tool call. See skill_store.record_tool_outcome()."""
        return self._store.record_tool_outcome(name, success, context=context)

    def suggest_skill(self, context: Optional[Dict] = None) -> Optional[Dict]:
        """Best-effort: of the skills actually built so far (active or
        suggested, never deprecated), return the one whose name best
        matches the words in `context` - or, if none match at all, the
        single highest-confidence active skill as a generic fallback.
        None if nothing has been learned yet."""
        candidates = self._store.list_skills(status=STATUS_ACTIVE, limit=50)
        candidates += self._store.list_skills(status=STATUS_SUGGESTED, limit=50)
        if not candidates:
            return None

        context_words = set()
        for value in (context or {}).values():
            if isinstance(value, str):
                context_words.update(value.lower().split())

        if context_words:

            def overlap(skill):
                name_words = set(skill["name"].lower().replace("_", " ").split())
                return len(name_words & context_words)

            best = max(candidates, key=overlap)
            if overlap(best) > 0:
                return best

        active = [c for c in candidates if c["status"] == STATUS_ACTIVE]
        pool = active or candidates
        return max(pool, key=lambda s: s["confidence"])

    # ---- passthroughs + bookkeeping ---------------------------------------------

    def improve_skill(self, skill_id: int) -> Dict:
        return self._improver.apply(skill_id)

    def list_skills(self, status: Optional[str] = None, limit: int = 50) -> List[Dict]:
        return self._store.list_skills(status=status, limit=limit)

    def get_skill(self, skill_id: int) -> Optional[Dict]:
        return self._store.get_skill(skill_id)

    def _log_run(self, trigger: str, outcome: str, skill_id: Optional[int], detail: str) -> int:
        now = time.time()
        with self._lock:
            cur = self._conn.execute(
                """INSERT INTO builder_runs (trigger, outcome, skill_id, detail, timestamp)
                   VALUES (?, ?, ?, ?, ?)""",
                (trigger, outcome, skill_id, detail, now),
            )
            self._conn.commit()
            return cur.lastrowid

    def get_history(self, limit: int = 20) -> List[Dict]:
        with self._lock:
            cur = self._conn.execute(
                """SELECT id, trigger, outcome, skill_id, detail, timestamp
                   FROM builder_runs ORDER BY id DESC LIMIT ?""",
                (limit,),
            )
            rows = cur.fetchall()
        return [
            {"id": r[0], "trigger": r[1], "outcome": r[2], "skill_id": r[3], "detail": r[4], "timestamp": r[5]}
            for r in rows
        ]


def get_skill_builder_engine() -> SkillBuilderEngine:
    """Process-wide SkillBuilderEngine singleton."""
    global _instance
    if _instance is None:
        with _instance_lock:
            if _instance is None:
                _instance = SkillBuilderEngine()
    return _instance
