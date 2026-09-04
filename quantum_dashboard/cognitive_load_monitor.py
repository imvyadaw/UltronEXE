"""
cognitive_load_monitor.py
===========================
A rough "how scattered is my work right now" indicator, built from
two signals: how often the foreground app is changing, and how long
since the last input. Frequent app-switching + little idle time tends
to mean fragmented/reactive work; long unbroken stretches on one app
tend to mean focus.

This is a heuristic proxy, not a measurement of anything about the
user's mind - it's the same idea as "screen time" style app reports,
just weighted toward context-switching. It does not capture WHAT was
typed or clicked, only WHEN input happened and WHICH app had focus,
so it can't function as a keylogger even by accident. Treat the score
as a nudge ("been switching a lot the last 20 min, want me to hold
notifications?"), not a diagnosis of anything - please don't use it,
or let it be used, to make claims about someone's health or mental
state.

Dependencies: pip install pywin32 psutil
"""

from __future__ import annotations

import logging
import threading
import time
from collections import deque
from dataclasses import dataclass
from typing import Callable, Deque, Optional

import win32gui
import win32api

logger = logging.getLogger("ultron.cognitive_load_monitor")


@dataclass
class LoadReading:
    timestamp: float
    switches_last_10min: int
    idle_seconds: float
    load_score: int  # 0-100, higher = more fragmented/switch-heavy
    label: str  # "focused" | "moderate" | "fragmented"


def _idle_seconds() -> float:
    """Seconds since the last mouse/keyboard input, via the Win32
    GetLastInputInfo API. Only timing is read - no key or click data."""
    try:
        import ctypes

        class LASTINPUTINFO(ctypes.Structure):
            _fields_ = [("cbSize", ctypes.c_uint), ("dwTime", ctypes.c_uint)]

        lii = LASTINPUTINFO()
        lii.cbSize = ctypes.sizeof(LASTINPUTINFO)
        ctypes.windll.user32.GetLastInputInfo(ctypes.byref(lii))
        millis_idle = win32api.GetTickCount() - lii.dwTime
        return millis_idle / 1000.0
    except Exception:
        return 0.0


class CognitiveLoadMonitor:
    def __init__(self, window_minutes: int = 10, sample_interval: float = 5.0):
        self.window_minutes = window_minutes
        self.sample_interval = sample_interval
        self._switch_timestamps: Deque[float] = deque()
        self._last_foreground: Optional[int] = None
        self._on_reading: Optional[Callable[[LoadReading], None]] = None
        self._thread: Optional[threading.Thread] = None
        self._running = False

    def on_reading(self, callback: Callable[[LoadReading], None]):
        self._on_reading = callback

    def _record_switch_if_changed(self):
        hwnd = win32gui.GetForegroundWindow()
        if hwnd and hwnd != self._last_foreground:
            self._last_foreground = hwnd
            self._switch_timestamps.append(time.time())

    def _prune_window(self):
        cutoff = time.time() - self.window_minutes * 60
        while self._switch_timestamps and self._switch_timestamps[0] < cutoff:
            self._switch_timestamps.popleft()

    def current_reading(self) -> LoadReading:
        self._record_switch_if_changed()
        self._prune_window()

        switches = len(self._switch_timestamps)
        idle = _idle_seconds()

        # Simple, transparent scoring - not a validated psychological
        # instrument, just a readable heuristic:
        #   0-4 switches/10min  -> low
        #   5-12                -> moderate
        #   13+                 -> high
        # Long idle time pulls the score down (probably stepped away).
        if idle > 120:
            score = max(0, 20 - int(idle / 60))
        else:
            score = min(100, switches * 7)

        if score < 30:
            label = "focused"
        elif score < 65:
            label = "moderate"
        else:
            label = "fragmented"

        return LoadReading(
            timestamp=time.time(),
            switches_last_10min=switches,
            idle_seconds=round(idle, 1),
            load_score=score,
            label=label,
        )

    def _loop(self):
        while self._running:
            reading = self.current_reading()
            if self._on_reading:
                self._on_reading(reading)
            time.sleep(self.sample_interval)

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        logger.info(
            "CognitiveLoadMonitor sampling every %.1fs over a %d-min window", self.sample_interval, self.window_minutes
        )

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=2)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    clm = CognitiveLoadMonitor()
    clm.on_reading(
        lambda r: print(f"[{r.label}] score={r.load_score} switches={r.switches_last_10min} idle={r.idle_seconds}s")
    )
    clm.start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        clm.stop()
