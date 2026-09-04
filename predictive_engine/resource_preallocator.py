"""
resource_preallocator.py
===========================
Given a ranked list of predicted next actions (from
NextActionPredictor), pre-warms whatever resource a caller has
registered for that action - e.g. spin up a subprocess handle,
open a DB connection pool, warm an in-memory cache - *before* the
user actually asks for it, so the real request feels instant.

This module deliberately does NOT decide what "pre-warming" means.
It's a thin, generic scheduler: you register a
`(action_name -> callable)` map, it calls the callable when that
action clears a confidence threshold, and it tracks a short cooldown
so the same resource isn't repeatedly re-warmed. What the callable
actually does (open a file handle, ping an API, pre-load a model)
is entirely up to the caller/skill author.

Dependencies: none beyond the standard library.
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional

from .next_action_predictor import Prediction

logger = logging.getLogger("ultron.resource_preallocator")


@dataclass
class PreallocResult:
    action: str
    triggered: bool
    detail: str = ""


class ResourcePreallocator:
    """Runs registered pre-warm callbacks for high-confidence predictions."""

    def __init__(self, confidence_threshold: float = 0.4, cooldown_seconds: float = 60.0):
        self.confidence_threshold = confidence_threshold
        self.cooldown_seconds = cooldown_seconds
        self._handlers: Dict[str, Callable[[], None]] = {}
        self._teardown: Dict[str, Callable[[], None]] = {}
        self._last_triggered: Dict[str, float] = {}
        self._lock = threading.Lock()

    def register(self, action: str, warm_fn: Callable[[], None], cool_fn: Optional[Callable[[], None]] = None):
        """Register what to do to pre-warm `action`, and optionally how to release it later."""
        self._handlers[action] = warm_fn
        if cool_fn:
            self._teardown[action] = cool_fn
        logger.debug("Registered preallocator handler for '%s'", action)

    def unregister(self, action: str):
        self._handlers.pop(action, None)
        self._teardown.pop(action, None)

    def process(self, predictions: List[Prediction]) -> List[PreallocResult]:
        """Fire pre-warm callbacks for any prediction above threshold and off cooldown."""
        results = []
        now = time.monotonic()
        with self._lock:
            for pred in predictions:
                if pred.confidence < self.confidence_threshold:
                    continue
                handler = self._handlers.get(pred.action)
                if handler is None:
                    continue
                last = self._last_triggered.get(pred.action, 0.0)
                if now - last < self.cooldown_seconds:
                    results.append(PreallocResult(pred.action, False, "cooldown active"))
                    continue
                try:
                    handler()
                    self._last_triggered[pred.action] = now
                    results.append(PreallocResult(pred.action, True, f"warmed at confidence {pred.confidence}"))
                    logger.info(
                        "Pre-warmed resource for predicted action '%s' (confidence=%.2f)", pred.action, pred.confidence
                    )
                except Exception as exc:  # a bad pre-warm callback should never crash the assistant
                    logger.error("Pre-warm handler for '%s' failed: %s", pred.action, exc)
                    results.append(PreallocResult(pred.action, False, f"error: {exc}"))
        return results

    def release_idle(self, active_actions: Optional[List[str]] = None):
        """Call teardown for any warmed resource not in `active_actions` (or all, if None)."""
        active = set(active_actions or [])
        with self._lock:
            for action in list(self._last_triggered):
                if action in active:
                    continue
                teardown = self._teardown.get(action)
                if teardown:
                    try:
                        teardown()
                        logger.debug("Released pre-warmed resource for '%s'", action)
                    except Exception as exc:
                        logger.error("Teardown for '%s' failed: %s", action, exc)
                self._last_triggered.pop(action, None)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    pre = ResourcePreallocator(confidence_threshold=0.1, cooldown_seconds=5)
    pre.register("open_app:vscode", warm_fn=lambda: print("-> pretend-launching vscode splash cache"))
    demo_predictions = [Prediction(action="open_app:vscode", confidence=0.8, reason="demo")]
    print(pre.process(demo_predictions))
