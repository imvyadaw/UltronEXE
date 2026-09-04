"""
Error handling hardening (Phase 29.3)
========================================
core/error_handler.py's ErrorHandler.run_safely() already classifies
and retries a *single* call. What it doesn't do - by design, it's a
per-call helper, not a subsystem-level policy - is notice that one
context has failed 20 times in a row and stop hammering it: every new
call still pays the full retry+backoff cost even though the last 19
calls to that same context all failed the same way.

HardenedErrorHandler adds that layer on top, without changing
ErrorHandler itself: a simple per-context circuit breaker.

    CLOSED   - normal; every call goes through run_safely() as before.
    OPEN     - this context has failed >= failure_threshold times in a
               row; new calls short-circuit immediately (no retry, no
               backoff, no call to func at all) until cooldown_seconds
               has passed.
    HALF_OPEN - cooldown elapsed; the next call is allowed through as a
               probe. Success closes the circuit and resets the streak;
               failure re-opens it and restarts the cooldown.

This is deliberately in-memory/per-process only, matching
core/perf_trace.py's stated non-goal of being a persisted store - it
protects the current run from cascading failures, not a historical
record (that's what deploy_check.py's report + database persistence in
perf_optimizer.py are for).
"""

import threading
import time
from dataclasses import dataclass
from typing import Callable, Dict, Optional

from core.error_handler import get_error_handler

DEFAULT_FAILURE_THRESHOLD = 5
DEFAULT_COOLDOWN_SECONDS = 30.0


@dataclass
class _CircuitState:
    consecutive_failures: int = 0
    state: str = "closed"  # closed | open | half_open
    opened_at: float = 0.0
    total_calls: int = 0
    total_failures: int = 0
    total_short_circuited: int = 0


class HardenedErrorHandler:
    def __init__(
        self,
        failure_threshold: int = DEFAULT_FAILURE_THRESHOLD,
        cooldown_seconds: float = DEFAULT_COOLDOWN_SECONDS,
    ):
        self._eh = get_error_handler()
        self._lock = threading.Lock()
        self._circuits: Dict[str, _CircuitState] = {}
        self.failure_threshold = failure_threshold
        self.cooldown_seconds = cooldown_seconds

    def _circuit(self, context: str) -> _CircuitState:
        if context not in self._circuits:
            self._circuits[context] = _CircuitState()
        return self._circuits[context]

    def run_safely(self, func: Callable, *args, context: str = "", **kwargs) -> Dict:
        ctx = context or getattr(func, "__name__", "call")
        with self._lock:
            c = self._circuit(ctx)
            c.total_calls += 1
            if c.state == "open":
                if time.time() - c.opened_at >= self.cooldown_seconds:
                    c.state = "half_open"
                else:
                    c.total_short_circuited += 1
                    return {
                        "success": False,
                        "error": f"circuit open for '{ctx}' ({c.consecutive_failures} consecutive "
                        f"failures) - retry after {self.cooldown_seconds - (time.time() - c.opened_at):.0f}s",
                        "category": "circuit_open",
                        "attempts": 0,
                    }

        # The actual call happens outside the lock - ErrorHandler.run_safely
        # can sleep between retries and must never hold this lock while doing so.
        result = self._eh.run_safely(func, *args, context=context, **kwargs)

        with self._lock:
            c = self._circuit(ctx)
            if result.get("success"):
                c.consecutive_failures = 0
                c.state = "closed"
            else:
                c.consecutive_failures += 1
                c.total_failures += 1
                if c.consecutive_failures >= self.failure_threshold:
                    c.state = "open"
                    c.opened_at = time.time()
        return result

    def status(self) -> Dict[str, Dict]:
        with self._lock:
            return {
                ctx: {
                    "state": c.state,
                    "consecutive_failures": c.consecutive_failures,
                    "total_calls": c.total_calls,
                    "total_failures": c.total_failures,
                    "total_short_circuited": c.total_short_circuited,
                }
                for ctx, c in self._circuits.items()
            }

    def reset(self, context: Optional[str] = None) -> None:
        with self._lock:
            if context is None:
                self._circuits.clear()
            else:
                self._circuits.pop(context, None)


_hardened: Optional[HardenedErrorHandler] = None


def get_hardened_handler() -> HardenedErrorHandler:
    global _hardened
    if _hardened is None:
        _hardened = HardenedErrorHandler()
    return _hardened
