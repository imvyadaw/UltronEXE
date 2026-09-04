"""
Stop Conditions (Phase 30 - Autonomy)
========================================
cognitive_core/autonomous_executor.py already bounds itself with two
hard-coded constants (MAX_SUBGOAL_ATTEMPTS, MAX_TOTAL_STEPS) and
core/autonomous_engine.py has its own separate limits - each loop
re-invents "when do I stop" on its own, and none of them can be told
to stop early from outside (e.g. the user saying "stop" mid-run, or
core/orchestrator.py deciding a goal is no longer worth pursuing).

StopConditions is one reusable, poll-per-iteration safety gate any
loop can hold an instance of and call should_stop() on before
starting its next step. It doesn't replace the existing per-module
ceilings (autonomous_executor.py's MAX_TOTAL_STEPS still applies
inside its own workflow_engine calls) - it's the gate
core/orchestrator.py's own higher-level loop uses, and any future
caller can adopt without needing autonomous_executor.py's internals.

Trip conditions, checked in this order (first match wins):
    1. external abort  - request_stop() was called (user/UI signal)
    2. max_iterations   - hard step ceiling for this run
    3. max_duration     - wall-clock ceiling for this run
    4. consecutive_failures - N failed steps in a row with no success
                              between them (thrashing / stuck loop)
"""

import threading
import time
from dataclasses import dataclass

from core.logger import get_logger

logger = get_logger("ultron.autonomy.stop_conditions")


@dataclass
class StopCheck:
    stopped: bool
    reason: str = ""


class StopConditions:
    def __init__(
        self, max_iterations: int = 50, max_duration_seconds: float = 900.0, max_consecutive_failures: int = 3
    ):
        self.max_iterations = max_iterations
        self.max_duration_seconds = max_duration_seconds
        self.max_consecutive_failures = max_consecutive_failures

        self._lock = threading.Lock()
        self._iterations = 0
        self._consecutive_failures = 0
        self._start_time = time.time()
        self._abort_requested = False
        self._abort_reason = ""

    def record_iteration(self, success: bool):
        with self._lock:
            self._iterations += 1
            if success:
                self._consecutive_failures = 0
            else:
                self._consecutive_failures += 1

    def request_stop(self, reason: str = "user requested stop"):
        with self._lock:
            self._abort_requested = True
            self._abort_reason = reason
        logger.info(f"Stop requested: {reason}")

    def should_stop(self) -> StopCheck:
        with self._lock:
            if self._abort_requested:
                return StopCheck(True, self._abort_reason)
            if self._iterations >= self.max_iterations:
                return StopCheck(True, f"max_iterations reached ({self.max_iterations})")
            elapsed = time.time() - self._start_time
            if elapsed >= self.max_duration_seconds:
                return StopCheck(True, f"max_duration_seconds reached ({self.max_duration_seconds}s)")
            if self._consecutive_failures >= self.max_consecutive_failures:
                return StopCheck(True, f"{self._consecutive_failures} consecutive failures")
            return StopCheck(False)

    def reset(self):
        with self._lock:
            self._iterations = 0
            self._consecutive_failures = 0
            self._start_time = time.time()
            self._abort_requested = False
            self._abort_reason = ""

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "iterations": self._iterations,
                "consecutive_failures": self._consecutive_failures,
                "elapsed_seconds": round(time.time() - self._start_time, 1),
                "abort_requested": self._abort_requested,
            }


def new_stop_conditions(
    max_iterations: int = 50, max_duration_seconds: float = 900.0, max_consecutive_failures: int = 3
) -> StopConditions:
    """Unlike most get_xxx() singletons in this codebase, stop
    conditions are per-run state (each goal/task_loop run needs its
    own fresh budget), so this is a factory, not a singleton."""
    return StopConditions(max_iterations, max_duration_seconds, max_consecutive_failures)
