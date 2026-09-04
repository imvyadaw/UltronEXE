"""Learning guardian
================
policy.py and review_queue.py gate *new* autonomy (a procedure earning
enough trust to run on its own). This module watches the *existing*
autonomy learning_scheduler.py already had before Phase 4.5 - the
recurring consolidate/scan/promote/forget cycle - for a run that went
wrong in a way no single step's own error handling would catch, because
each step already returns cleanly whether or not what it did was
sensible:

    - a cycle whose forgetting.py step pruned an unusually large slice
      of all current patterns or episodes in one pass. Ordinary decay
      is gradual by construction (learning/confidence.py's curve
      asymptotically approaches its floor); a sudden large fraction
      pruned in a single cycle is a shape decay doesn't produce on its
      own, and looks like a bug (a bad threshold, a clock problem) more
      than legitimate forgetting.
    - several consecutive cycles that raised an exception
      (learning_scheduler.py already catches and records these in
      `result["success"]`/`result["error"]`, but nothing previously
      read that record and reacted to a streak of them).

check_cycle() is meant to be called once per learning_scheduler.py
cycle, right after it finishes. A `halt: True` result means "stop the
recurring schedule and wait for a human to look" - learning_scheduler.py
is the one place that actually calls self.stop() on that signal; this
module only ever raises the flag, it doesn't reach into the scheduler
itself, same "detect vs. act stay separate" split as
learning/failure_learner.py's should_caution() vs. whatever calls it.

In-memory only, matching learning_scheduler.py's own `_history` - the
durable record of what happened is already in
storage/learning/forgetting_log.json and whatever the cycle itself
wrote; incidents() here is just "did anything look wrong recently",
not a second audit trail.
"""

import time
from typing import Dict, List, Optional

from core.logger import get_logger

logger = get_logger("safety.guardian")

# More than a quarter of all current patterns/episodes pruned in a
# single cycle is treated as a spike rather than gradual decay.
MAX_PRUNE_FRACTION_PER_CYCLE = 0.25
MAX_CONSECUTIVE_CYCLE_FAILURES = 3


class LearningGuardian:
    """Flags a learning_scheduler.py cycle result as something a human should look at, rather than trusting every cycle."""

    def __init__(self):
        self._consecutive_failures = 0
        self._incidents: List[Dict] = []

    def check_cycle(
        self,
        cycle_result: Dict,
        total_patterns_before: Optional[int] = None,
        total_episodes_before: Optional[int] = None,
    ) -> Dict:
        """`total_patterns_before`/`total_episodes_before` are counts
        the caller took *before* running the cycle (learning_scheduler.py
        does this) - comparing against a snapshot from before this
        cycle's own pruning, not against whatever's left after."""
        try:
            incidents = []

            if not cycle_result.get("success", True):
                self._consecutive_failures += 1
                if self._consecutive_failures >= MAX_CONSECUTIVE_CYCLE_FAILURES:
                    incidents.append(
                        {
                            "type": "repeated_cycle_failure",
                            "detail": f"{self._consecutive_failures} consecutive failed cycles "
                            f"(latest: {cycle_result.get('error', 'unknown error')})",
                        }
                    )
            else:
                self._consecutive_failures = 0

            forgetting = cycle_result.get("forgetting") or {}
            pattern_prune_count = (forgetting.get("patterns") or {}).get("count", 0)
            episode_prune_count = (forgetting.get("episodes") or {}).get("count", 0)

            if total_patterns_before and pattern_prune_count / total_patterns_before > MAX_PRUNE_FRACTION_PER_CYCLE:
                incidents.append(
                    {
                        "type": "pattern_prune_spike",
                        "detail": f"pruned {pattern_prune_count}/{total_patterns_before} patterns in one cycle",
                    }
                )
            if total_episodes_before and episode_prune_count / total_episodes_before > MAX_PRUNE_FRACTION_PER_CYCLE:
                incidents.append(
                    {
                        "type": "episode_prune_spike",
                        "detail": f"pruned {episode_prune_count}/{total_episodes_before} episodes in one cycle",
                    }
                )

            for incident in incidents:
                incident["detected_at"] = time.time()
                self._incidents.append(incident)
                logger.warning(f"Learning guardian incident: {incident['type']} - {incident['detail']}")

            return {"halt": len(incidents) > 0, "incidents": incidents}
        except Exception as e:
            logger.error(f"check_cycle() failed: {e}")
            # A guardian error is not itself grounds to halt an
            # otherwise-fine cycle - fail open on the halt decision,
            # but still surface the error for visibility.
            return {"halt": False, "incidents": [], "error": str(e)}

    def incidents(self, limit: int = 20) -> Dict:
        entries = self._incidents[-limit:][::-1]
        return {"count": len(entries), "entries": entries}

    def reset(self) -> None:
        """Clear the consecutive-failure streak - e.g. after a human has
        looked into a halted scheduler and is about to restart it."""
        self._consecutive_failures = 0


_guardian: Optional[LearningGuardian] = None


def get_learning_guardian() -> LearningGuardian:
    global _guardian
    if _guardian is None:
        _guardian = LearningGuardian()
    return _guardian
