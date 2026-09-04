"""
Performance
===========
Lightweight timing utilities for measuring how long parts of Ultron take -
a tool call, an LLM round-trip, a plan execution - without needing a full
profiler. Results feed monitoring/alerts.py (e.g. "cloud response time
p95 > 5s") and are handy for the same kind of debugging
ai/ai_router.py's own self.stats already does for cloud vs local calls,
generalized so any module can use it.

Two ways to use it:
    with PerformanceTracker().track("plan_and_run"):
        ...

    tracker = PerformanceTracker()
    tracker.start("step_1")
    ...
    tracker.stop("step_1")
"""

import statistics
import time
from contextlib import contextmanager
from typing import Dict, List


class PerformanceTracker:
    """Record named timing samples and summarize them (avg/min/max/p95)."""

    def __init__(self):
        self._samples: Dict[str, List[float]] = {}
        self._in_progress: Dict[str, float] = {}

    def start(self, label: str) -> None:
        self._in_progress[label] = time.perf_counter()

    def stop(self, label: str) -> Dict:
        started = self._in_progress.pop(label, None)
        if started is None:
            return {"error": f"No in-progress timer named '{label}' - call start() first"}
        elapsed = time.perf_counter() - started
        self._samples.setdefault(label, []).append(elapsed)
        return {"label": label, "elapsed_seconds": round(elapsed, 4)}

    @contextmanager
    def track(self, label: str):
        """Context-manager form: `with tracker.track('name'): ...`"""
        self.start(label)
        try:
            yield
        finally:
            self.stop(label)

    def summary(self, label: str) -> Dict:
        """avg/min/max/p95 for every sample recorded under `label`."""
        samples = self._samples.get(label, [])
        if not samples:
            return {"label": label, "count": 0}

        sorted_samples = sorted(samples)
        p95_index = min(len(sorted_samples) - 1, int(len(sorted_samples) * 0.95))

        return {
            "label": label,
            "count": len(samples),
            "avg_seconds": round(statistics.mean(samples), 4),
            "min_seconds": round(min(samples), 4),
            "max_seconds": round(max(samples), 4),
            "p95_seconds": round(sorted_samples[p95_index], 4),
        }

    def all_summaries(self) -> Dict:
        return {label: self.summary(label) for label in self._samples}

    def reset(self, label: str = None) -> None:
        """Clear samples for one label, or everything if label is omitted."""
        if label is None:
            self._samples.clear()
        else:
            self._samples.pop(label, None)


_tracker = None


def get_performance_tracker() -> PerformanceTracker:
    """Shared PerformanceTracker instance so samples accumulate across
    modules instead of each caller starting from an empty tracker."""
    global _tracker
    if _tracker is None:
        _tracker = PerformanceTracker()
    return _tracker
