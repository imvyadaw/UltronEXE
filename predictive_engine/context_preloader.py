"""
context_preloader.py
=======================
Pre-fetches lightweight *context* (not heavy resources - see
resource_preallocator.py for that) that predicted actions are likely
to need: e.g. if "check_calendar" is predicted, warm a cached copy
of today's events; if "open_app:vscode" is predicted, cache the list
of recently-edited project files. Results are held in a short-lived
in-memory cache with a TTL so stale context never lingers.

Like resource_preallocator, this module is generic: callers register
`action -> fetch_fn` mappings; the fetch functions do the actual work
(hitting a calendar API, reading recent files, etc).

Dependencies: none beyond the standard library.
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

from .next_action_predictor import Prediction

logger = logging.getLogger("ultron.context_preloader")


@dataclass
class _CacheEntry:
    value: Any
    fetched_at: float
    ttl_seconds: float

    @property
    def expired(self) -> bool:
        return (time.monotonic() - self.fetched_at) > self.ttl_seconds


class ContextPreloader:
    """Prefetches and caches lightweight context for predicted actions."""

    def __init__(self, default_ttl_seconds: float = 300.0, confidence_threshold: float = 0.3):
        self.default_ttl_seconds = default_ttl_seconds
        self.confidence_threshold = confidence_threshold
        self._fetchers: Dict[str, Callable[[], Any]] = {}
        self._ttls: Dict[str, float] = {}
        self._cache: Dict[str, _CacheEntry] = {}
        self._lock = threading.Lock()

    def register(self, action: str, fetch_fn: Callable[[], Any], ttl_seconds: Optional[float] = None):
        self._fetchers[action] = fetch_fn
        self._ttls[action] = ttl_seconds or self.default_ttl_seconds

    def preload(self, predictions: List[Prediction]) -> Dict[str, bool]:
        """Fetch context for any high-confidence prediction not already cached (or stale)."""
        results = {}
        with self._lock:
            for pred in predictions:
                if pred.confidence < self.confidence_threshold:
                    continue
                fetcher = self._fetchers.get(pred.action)
                if fetcher is None:
                    continue
                entry = self._cache.get(pred.action)
                if entry and not entry.expired:
                    results[pred.action] = False  # already fresh, nothing to do
                    continue
                try:
                    value = fetcher()
                    self._cache[pred.action] = _CacheEntry(value, time.monotonic(), self._ttls[pred.action])
                    results[pred.action] = True
                    logger.info("Preloaded context for '%s'", pred.action)
                except Exception as exc:
                    logger.error("Context fetch for '%s' failed: %s", pred.action, exc)
                    results[pred.action] = False
        return results

    def get(self, action: str) -> Optional[Any]:
        """Return cached context for `action` if present and fresh, else None."""
        with self._lock:
            entry = self._cache.get(action)
            if entry and not entry.expired:
                return entry.value
            return None

    def invalidate(self, action: Optional[str] = None):
        with self._lock:
            if action:
                self._cache.pop(action, None)
            else:
                self._cache.clear()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    preloader = ContextPreloader(confidence_threshold=0.1)
    preloader.register("check_calendar", fetch_fn=lambda: ["09:00 standup", "14:00 1:1"])
    demo = [Prediction(action="check_calendar", confidence=0.7, reason="demo")]
    print(preloader.preload(demo))
    print(preloader.get("check_calendar"))
