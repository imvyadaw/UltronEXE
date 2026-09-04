"""
Latency tracer (T0-T7)
========================
Lightweight per-turn timing so pipeline latency can be measured instead
of guessed at, ahead of any further "make it faster" optimizations
(TTS caching, warm-up, VAD, ...) - each of those chunks can point at a
before/after summary() line from this module instead of "it feels
faster".

Stages tracked, matching the SUPER-FAST ULTRON spec:
    T0 = wake detected
    T1 = STT started
    T2 = STT completed
    T3 = auto-decision completed (which tier: simple/normal/complex)
    T4 = action/AI request started
    T5 = first AI output/token
    T6 = first TTS audio
    T7 = task/response completed

Deliberately NOT a general-purpose profiler or a persisted metrics
store - single current turn, in-memory only, one summary log line per
turn. That's enough to answer "which stage is slow" without adding any
real overhead to the hot path itself (a mark() call is a lock + one
dict write; summary() is the only place that does string formatting
and logging, called once per turn).

Some stages collapse into the same instant on some code paths - that's
not a bug, it's real: e.g. "Ultron, open Chrome" spoken as one
utterance has STT finish as part of wake-word detection, so T1 and T2
land at the very same moment T0 does for that turn. The summary output
reflects that honestly rather than inventing a gap that didn't happen.

Thread-safety note: only one voice turn is ever in flight at a time in
this codebase's current architecture (single mic, single wake-word
loop), so a single shared _marks dict guarded by one lock is enough -
this is not designed to trace concurrent/overlapping turns.
"""

import threading
import time

from config import PERF_TRACE_ENABLED
from core.logger import get_logger

logger = get_logger("ultron.perf")

_STAGE_ORDER = [
    "T0_wake",
    "T1_stt_start",
    "T2_stt_done",
    "T3_decision",
    "T4_request_start",
    "T5_first_output",
    "T6_first_audio",
    "T7_done",
]

_lock = threading.Lock()
_marks = {}


def start_turn():
    """Begin a brand-new turn - always resets, discarding any previous
    turn's marks. Call this at the *genuine* start of a turn (wake word
    just fired); for anything else that needs a turn to exist but isn't
    sure one has already started (e.g. handle_command(), which is also
    reachable from typed-input modes that never go through the wake
    path), use ensure_turn() instead so an in-progress voice turn's
    T0/T1/T2 don't get wiped out."""
    if not PERF_TRACE_ENABLED:
        return
    with _lock:
        _marks.clear()
        now = time.monotonic()
        _marks["_t_start"] = now
        _marks["T0_wake"] = now


def ensure_turn():
    """Start a turn only if one isn't already in progress. Safe to call
    at the top of any entry point that sometimes has a turn already
    started upstream (run_listen's on_wake) and sometimes doesn't
    (typed/text-mode callers going straight to handle_command)."""
    if not PERF_TRACE_ENABLED:
        return
    with _lock:
        if "_t_start" not in _marks:
            now = time.monotonic()
            _marks["_t_start"] = now
            _marks["T0_wake"] = now


def mark(stage: str):
    """Record that `stage` happened now - only the *first* call for a
    given stage in the current turn counts (later calls no-op), since
    T5/T6 in particular are meant to capture "first token" / "first
    audio", not the most recent one. No-ops silently (never raises) if
    tracing is disabled or no turn has been started - a missing mark()
    call site, or one that fires before start_turn()/ensure_turn(), is
    a no-op rather than a crash."""
    if not PERF_TRACE_ENABLED:
        return
    try:
        with _lock:
            if "_t_start" not in _marks or stage in _marks:
                return
            _marks[stage] = time.monotonic()
    except Exception:
        from core.error_trace import log_swallowed as _lsw

        _lsw("core.perf_trace.mark")


def summary() -> str:
    """Log (and return) one line summarizing this turn's stage timings:
    each stage that actually fired, how long after T0 it happened, and
    the delta from the previous stage that fired. Call once at the very
    end of a turn. Stages that never fired for this turn (e.g. T1/T2 on
    a combined wake+command utterance where STT happened before T0) are
    simply omitted rather than shown as zero or missing."""
    if not PERF_TRACE_ENABLED:
        return ""
    try:
        with _lock:
            if "_t_start" not in _marks:
                return ""
            t_start = _marks["_t_start"]
            present = [(s, _marks[s]) for s in _STAGE_ORDER if s in _marks]
        if not present:
            return ""
        parts = []
        prev_t = t_start
        for stage, t in present:
            since_start_ms = (t - t_start) * 1000
            delta_ms = (t - prev_t) * 1000
            parts.append(f"{stage}=+{since_start_ms:.0f}ms(d{delta_ms:.0f}ms)")
            prev_t = t
        line = "[perf] " + " ".join(parts)
        logger.info(line)
        return line
    except Exception:
        return ""
