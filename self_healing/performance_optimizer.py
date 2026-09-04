"""
performance_optimizer.py
===========================
Watches ULTRON's own process (not the whole system - see
health_monitor.py for that) over time and produces concrete, scoped
optimization suggestions: trim an in-memory cache that's grown past
a sane size, shrink a thread pool that's oversubscribed relative to
CPU count, flag a memory trend that looks like a leak. Callers can
also register `apply_fn` callbacks per suggestion kind so the ones
they're comfortable auto-applying happen without manual intervention;
anything without a registered `apply_fn` is reported only.

Dependencies: pip install psutil
"""

from __future__ import annotations

import logging
import os
import threading
import time
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional

import psutil

logger = logging.getLogger("ultron.performance_optimizer")


@dataclass
class Suggestion:
    kind: str  # "trim_cache" | "shrink_thread_pool" | "possible_leak"
    detail: str
    applied: bool = False


class PerformanceOptimizer:
    """Tracks ULTRON's own process metrics over time and proposes/self-tunes optimizations."""

    def __init__(self, sample_window: int = 20, leak_growth_mb_threshold: float = 50.0):
        self.process = psutil.Process(os.getpid())
        self.sample_window = sample_window
        self.leak_growth_mb_threshold = leak_growth_mb_threshold
        self._samples: List[float] = []  # memory_mb over time
        self._lock = threading.Lock()
        self._apply_fns: Dict[str, Callable[[], None]] = {}
        self._cache_size_probes: Dict[str, Callable[[], int]] = {}
        self._cache_trim_fns: Dict[str, Callable[[], None]] = {}

    def register_apply(self, kind: str, apply_fn: Callable[[], None]):
        self._apply_fns[kind] = apply_fn

    def register_cache(
        self, name: str, size_probe: Callable[[], int], trim_fn: Callable[[], None], max_size: int = 10000
    ):
        """Register a cache ULTRON owns so this module can watch and optionally trim it."""
        self._cache_size_probes[name] = size_probe
        self._cache_trim_fns[name] = trim_fn
        self._max_cache_sizes = getattr(self, "_max_cache_sizes", {})
        self._max_cache_sizes[name] = max_size

    def sample(self):
        mem_mb = self.process.memory_info().rss / (1024 * 1024)
        with self._lock:
            self._samples.append(mem_mb)
            if len(self._samples) > self.sample_window:
                self._samples = self._samples[-self.sample_window :]

    def _check_leak(self) -> Optional[Suggestion]:
        with self._lock:
            if len(self._samples) < self.sample_window:
                return None
            growth = self._samples[-1] - self._samples[0]
        if growth >= self.leak_growth_mb_threshold:
            return Suggestion(
                "possible_leak",
                f"Memory grew {growth:.1f}MB over the last {self.sample_window} samples "
                f"with no drop - worth checking for a leak",
            )
        return None

    def _check_caches(self) -> List[Suggestion]:
        suggestions = []
        max_sizes = getattr(self, "_max_cache_sizes", {})
        for name, probe in self._cache_size_probes.items():
            try:
                size = probe()
            except Exception as exc:
                logger.error("Cache size probe '%s' failed: %s", name, exc)
                continue
            limit = max_sizes.get(name, 10000)
            if size > limit:
                suggestions.append(Suggestion("trim_cache", f"Cache '{name}' has {size} entries (limit {limit})"))
        return suggestions

    def _check_thread_pool(self) -> Optional[Suggestion]:
        cpu_count = psutil.cpu_count(logical=True) or 4
        num_threads = self.process.num_threads()
        if num_threads > cpu_count * 4:
            return Suggestion(
                "shrink_thread_pool",
                f"{num_threads} threads running against {cpu_count} logical CPUs - " f"likely oversubscribed",
            )
        return None

    def analyze(self, auto_apply: bool = True) -> List[Suggestion]:
        self.sample()
        suggestions: List[Suggestion] = []

        leak = self._check_leak()
        if leak:
            suggestions.append(leak)

        suggestions.extend(self._check_caches())

        pool = self._check_thread_pool()
        if pool:
            suggestions.append(pool)

        if auto_apply:
            for s in suggestions:
                if s.kind == "trim_cache":
                    # trim_cache suggestions carry the cache name in detail; apply all registered trims
                    for trim_fn in self._cache_trim_fns.values():
                        try:
                            trim_fn()
                        except Exception as exc:
                            logger.error("Cache trim failed: %s", exc)
                    s.applied = True
                elif s.kind in self._apply_fns:
                    try:
                        self._apply_fns[s.kind]()
                        s.applied = True
                    except Exception as exc:
                        logger.error("Apply function for '%s' failed: %s", s.kind, exc)

        for s in suggestions:
            logger.info("[%s]%s %s", s.kind, " (applied)" if s.applied else "", s.detail)
        return suggestions


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    optimizer = PerformanceOptimizer(sample_window=3)
    for _ in range(3):
        optimizer.sample()
        time.sleep(0.1)
    print(optimizer.analyze(auto_apply=False))
