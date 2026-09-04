"""
utils/timers.py - measuring elapsed time. Complements
utils.decorators.timed (whole-function timing) with a context-manager
form for timing a block, and a manual start/stop Stopwatch for cases
that don't fit either shape.
"""

from __future__ import annotations

import time
from types import TracebackType
from typing import Optional, Type

from utils.formatters import human_duration


class Timer:
    """Context manager that measures wall-clock time for a `with` block.

    >>> with Timer() as t:
    ...     pass
    >>> t.elapsed_seconds >= 0
    True
    """

    def __init__(self, label: str = ""):
        self.label = label
        self.elapsed_seconds: float = 0.0
        self._start: Optional[float] = None

    def __enter__(self) -> "Timer":
        self._start = time.perf_counter()
        return self

    def __exit__(
        self,
        exc_type: Optional[Type[BaseException]],
        exc_val: Optional[BaseException],
        exc_tb: Optional[TracebackType],
    ) -> None:
        self.elapsed_seconds = time.perf_counter() - (self._start or time.perf_counter())

    def __str__(self) -> str:
        prefix = f"{self.label}: " if self.label else ""
        return f"{prefix}{human_duration(self.elapsed_seconds)}"


class Stopwatch:
    """Manual start/stop/lap timer for cases a `with` block doesn't fit
    (e.g. timing spans that cross callback boundaries).

    >>> sw = Stopwatch()
    >>> sw.start()
    >>> _ = sw.stop()
    >>> sw.elapsed_seconds >= 0
    True
    """

    def __init__(self) -> None:
        self._start: Optional[float] = None
        self.elapsed_seconds: float = 0.0
        self.laps: list[float] = []

    def start(self) -> None:
        self._start = time.perf_counter()
        self.laps = []

    def lap(self) -> float:
        if self._start is None:
            raise RuntimeError("Stopwatch.lap() called before start()")
        elapsed = time.perf_counter() - self._start
        self.laps.append(elapsed)
        return elapsed

    def stop(self) -> float:
        if self._start is None:
            raise RuntimeError("Stopwatch.stop() called before start()")
        self.elapsed_seconds = time.perf_counter() - self._start
        self._start = None
        return self.elapsed_seconds
