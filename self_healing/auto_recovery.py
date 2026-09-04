"""
auto_recovery.py
===================
Consumes alerts from health_monitor.py and crash_analyzer.py and
runs a registered recovery strategy - restart a specific ULTRON
component/thread, clear a cache, drop into a degraded fallback mode,
etc. Recovery strategies always act on ULTRON's own components
(things the caller explicitly registers a handler for) - this module
never reaches out to kill arbitrary OS processes or touch anything
outside what you wire up yourself.

Includes a simple backoff so a component that keeps failing doesn't
get restart-looped forever; after `max_attempts` within `window`, it
stops trying and raises to `on_exhausted` instead so a human can look
at it.

Dependencies: none beyond the standard library.
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional

from .health_monitor import HealthAlert, Severity

logger = logging.getLogger("ultron.auto_recovery")


@dataclass
class RecoveryAttempt:
    component: str
    strategy: str
    success: bool
    timestamp: float


class AutoRecovery:
    """Maps unhealthy components to recovery callbacks, with backoff/exhaustion handling."""

    def __init__(self, max_attempts: int = 3, window_seconds: float = 300.0):
        self.max_attempts = max_attempts
        self.window_seconds = window_seconds
        self._strategies: Dict[str, Callable[[], bool]] = {}
        self._history: Dict[str, List[float]] = {}
        self._on_exhausted: Optional[Callable[[str], None]] = None
        self._lock = threading.Lock()
        self.log: List[RecoveryAttempt] = []

    def register_strategy(self, component: str, recover_fn: Callable[[], bool]):
        """`recover_fn` should attempt the fix and return True/False for success."""
        self._strategies[component] = recover_fn

    def on_exhausted(self, callback: Callable[[str], None]):
        """Called when a component has failed recovery `max_attempts` times within the window."""
        self._on_exhausted = callback

    def _recent_attempts(self, component: str) -> List[float]:
        now = time.monotonic()
        history = self._history.get(component, [])
        history = [t for t in history if now - t <= self.window_seconds]
        self._history[component] = history
        return history

    def attempt_recovery(self, component: str) -> Optional[bool]:
        """Run the registered strategy for `component` if under the attempt budget."""
        strategy = self._strategies.get(component)
        if strategy is None:
            logger.debug("No recovery strategy registered for '%s'", component)
            return None

        with self._lock:
            recent = self._recent_attempts(component)
            if len(recent) >= self.max_attempts:
                logger.error(
                    "Recovery exhausted for '%s' (%d attempts in last %.0fs)",
                    component,
                    len(recent),
                    self.window_seconds,
                )
                if self._on_exhausted:
                    self._on_exhausted(component)
                return False

            self._history.setdefault(component, []).append(time.monotonic())

        try:
            success = strategy()
        except Exception as exc:
            logger.error("Recovery strategy for '%s' raised: %s", component, exc)
            success = False

        self.log.append(
            RecoveryAttempt(
                component, strategy.__name__ if hasattr(strategy, "__name__") else "custom", success, time.time()
            )
        )
        logger.info("Recovery attempt for '%s': %s", component, "succeeded" if success else "failed")
        return success

    def handle_alert(self, alert: HealthAlert):
        """Wire directly to HealthMonitor.on_alert - only acts on CRITICAL alerts."""
        if alert.severity != Severity.CRITICAL:
            return
        self.attempt_recovery(alert.metric)

    def reset_backoff(self, component: str):
        with self._lock:
            self._history.pop(component, None)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    recovery = AutoRecovery(max_attempts=2, window_seconds=60)

    attempts = {"n": 0}

    def restart_stt():
        attempts["n"] += 1
        print(f"pretend-restarting STT engine (attempt {attempts['n']})")
        return attempts["n"] >= 2  # succeeds on 2nd try

    recovery.register_strategy("stt_engine", restart_stt)
    print(recovery.attempt_recovery("stt_engine"))
    print(recovery.attempt_recovery("stt_engine"))
