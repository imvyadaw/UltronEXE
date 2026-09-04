"""core/error_trace.py - makes previously-silent `except: pass` blocks
visible without changing their behavior.

RELIABILITY POLISH PASS: a codebase-wide scan found 149 except-blocks
across ai/, voice/, ui/, core/, intelligence/, etc. that catch an
exception and do nothing else - not even a log line. That's fine for
"this dependency is optional, keep going" cases, but it also means real
bugs vanish with zero trace: something breaks, ULTRON quietly keeps
running in a half-working state, and there's no way to tell why short of
re-adding print statements by hand mid-debug.

log_swallowed() is a drop-in replacement for the bare `pass` in those
blocks. It does NOT change control flow - the caller still falls through
and continues exactly as it did before. All it adds is one line in the
existing logs/ultron.log (via core.logger.get_logger, same file every
other part of ULTRON already logs to - no new setup, no --debug flag
needed) naming what got swallowed and where.

Logged at WARNING, not DEBUG: core.logger.get_logger() defaults the
"ultron" logger to INFO, and a fresh logging.getLogger(<dotted context>)
child of it inherits that threshold. DEBUG messages would be filtered
out and never reach the file at all - i.e. silently doing nothing again,
just one layer further down. WARNING guarantees it actually lands in
logs/ultron.log on a completely normal run, no flags, no config.

Usage (inside an except block, exception need not be bound to a name):
    try:
        risky_optional_thing()
    except Exception:
        log_swallowed("skills.web.form_filler.fill_field")

To review what's actually failing after a normal session:
    grep "SWALLOWED" logs/ultron.log
"""
import logging

import sys

_logger = None  # lazy singleton - one shared logger, one file handler, not one per call site


def log_swallowed(context: str = "") -> None:
    """Log the currently-handled exception and return. Call this from
    inside an `except:` block in place of a bare `pass`. Safe to call
    even with no active exception (no-op) and never raises, so it can't
    turn a soft-fail path into a hard crash."""
    global _logger
    try:
        exc_type, exc_value, _ = sys.exc_info()
        if exc_type is None:
            return
        if _logger is None:
            from core.logger import get_logger

            _logger = get_logger("ultron.swallowed")
        _logger.warning("SWALLOWED %s at %s: %s", exc_type.__name__, context or "unknown", exc_value)
    except Exception:
        logging.getLogger(__name__).exception("Suppressed Exception")
