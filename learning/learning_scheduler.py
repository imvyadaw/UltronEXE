"""Learning scheduler
==================
Every module in learning/ + memory/'s Phase 4.3 subpackages exposes a
run_x() entry point, but nothing has ever called them except by hand or
one-off from a tool. This is the background job that does: on an
interval, in a fixed order that respects each step's dependencies on
the one before it, it runs the whole self-maintenance pipeline -

    1. learning.memory_consolidator.run_consolidation()
       -> internally runs pattern_detector.run_detection() first, then
          digests stale episodes and merges duplicate patterns.
    2. learning.failure_learner.run_scan()
       -> needs step 1's fresh procedural/episodic data to flag against.
    3. learning.skill_learner.promote_masters()
       -> needs step 1/2's procedural outcome counts to grade mastery.
    4. learning.forgetting.run_decay_cycle()
       -> runs last on purpose: it only prunes episodes step 1 already
          digested, so it must never run before consolidation has had a
          chance to fold them into a pattern first.

Built directly on automation/scheduler/task_scheduler.py (the same
low-level backend core/scheduler.py uses), not on core/scheduler.py
itself - core/scheduler.py's callback shape is "run one named tool via
core/executor.py", but a learning cycle is several plain Python calls
chained together with no need to go through tool dispatch at all.

Deliberately simple/heuristic like the rest of Phase 4: one recurring
task, run in-process, with each cycle's summary kept in a small
in-memory history (not persisted - the durable output of a cycle is
whatever it wrote into memory/semantic/, memory/procedural/,
storage/learning/failure_lessons.json and forgetting_log.json; this
history is just "did the last few cycles look healthy").

Phase 4.5: run_once() now snapshots pattern/episode counts before the
cycle runs and hands them, plus the finished cycle's own result, to
safety/guardian.py's check_cycle(). A `halt` verdict (a prune-fraction
spike, or several consecutive failed cycles) stops the recurring
schedule the same way stop() always has - a halted scheduler doesn't
retry on its own; a human needs to look at safety/guardian.py's
incidents() and call start() again once satisfied.
"""

import time
from typing import Dict, List, Optional

from core.logger import get_logger
from automation.scheduler.task_scheduler import get_scheduler
from memory.episodic import get_episodic_memory
from memory.semantic import get_semantic_pattern_memory
from learning.memory_consolidator import get_memory_consolidator
from learning.failure_learner import get_failure_learner
from learning.skill_learner import get_skill_learner
from learning.forgetting import get_forgetting
from safety.guardian import get_learning_guardian

logger = get_logger("learning_scheduler")

DEFAULT_INTERVAL_SECONDS = 6 * 60 * 60  # every 6 hours
MAX_HISTORY = 20


class LearningScheduler:
    """Runs the full learning/memory-maintenance pipeline on a recurring interval."""

    def __init__(self):
        self._backend = get_scheduler()
        self._episodic = get_episodic_memory()
        self._semantic = get_semantic_pattern_memory()
        self._guardian = get_learning_guardian()
        self._task_id: Optional[str] = None
        self._history: List[Dict] = []

    def run_once(self) -> Dict:
        """Run the whole pipeline one time, in dependency order. Safe to
        call directly (e.g. from a tool, or right after startup) without
        going through start()."""
        started = time.time()
        result: Dict = {"started_at": started}
        patterns_before = self._safe_count(self._semantic.get_patterns)
        episodes_before = self._safe_count(lambda: self._episodic.recent_episodes(limit=1000))
        try:
            result["consolidation"] = get_memory_consolidator().run_consolidation()
            result["failure_scan"] = get_failure_learner().run_scan()
            result["skill_promotion"] = get_skill_learner().promote_masters()
            result["forgetting"] = get_forgetting().run_decay_cycle()
            result["success"] = True
        except Exception as e:
            logger.error(f"run_once() cycle failed: {e}")
            result["success"] = False
            result["error"] = str(e)
        result["ended_at"] = time.time()
        result["duration_seconds"] = round(result["ended_at"] - started, 3)

        guard = self._guardian.check_cycle(result, patterns_before, episodes_before)
        result["guardian"] = guard
        if guard.get("halt") and self._task_id is not None:
            logger.warning("Learning guardian flagged an incident - pausing the recurring schedule")
            self.stop()

        self._history.append(result)
        self._history = self._history[-MAX_HISTORY:]
        logger.info(f"Learning cycle finished in {result['duration_seconds']}s (success={result['success']})")
        return result

    @staticmethod
    def _safe_count(fetch) -> Optional[int]:
        """Best-effort 'count' before a step that might change it - a
        failure here shouldn't block the cycle itself, it just means
        safety/guardian.py's prune-fraction check sits out this cycle."""
        try:
            data = fetch()
            return data.get("count") if isinstance(data, dict) and "error" not in data else None
        except Exception:
            return None

    def start(self, interval_seconds: float = DEFAULT_INTERVAL_SECONDS) -> Dict:
        """Begin running run_once() every `interval_seconds`. No-op if
        already running - call stop() first to change the interval."""
        if self._task_id is not None:
            return {"error": "Learning scheduler already running", "task_id": self._task_id}
        self._task_id = self._backend.run_every(interval_seconds, self.run_once)
        logger.info(f"Learning scheduler started, interval={interval_seconds}s")
        return {"success": True, "task_id": self._task_id, "interval_seconds": interval_seconds}

    def stop(self) -> Dict:
        if self._task_id is None:
            return {"error": "Learning scheduler is not running"}
        cancelled = self._backend.cancel(self._task_id)
        self._task_id = None
        return {"success": cancelled}

    def status(self) -> Dict:
        return {
            "running": self._task_id is not None,
            "task_id": self._task_id,
            "recent_guardian_incidents": self._guardian.incidents(limit=5)["count"],
            "cycles_run": len(self._history),
            "last_cycle": self._history[-1] if self._history else None,
        }

    def history(self, limit: int = MAX_HISTORY) -> Dict:
        entries = self._history[-limit:][::-1]
        return {"count": len(entries), "entries": entries}


_learning_scheduler: Optional[LearningScheduler] = None


def get_learning_scheduler() -> LearningScheduler:
    global _learning_scheduler
    if _learning_scheduler is None:
        _learning_scheduler = LearningScheduler()
    return _learning_scheduler
