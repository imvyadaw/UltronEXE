"""
Startup
=======
Boot sequence run once before core.assistant.Assistant takes over: pokes
each subsystem that would otherwise fail silently or only surface an
error three commands into a session, and reports back a short pass/fail
summary. Called from main.py right after the banner, before the client
and command processor are constructed.

Deliberately never raises - a failing check is reported and logged, but
Ultron still starts (same "degrade, don't crash" philosophy as
core/events.py's EventBus and core/error_handler.py). The one exception
callers may care about is the GROQ_API_KEY check, which is informational
here too - ai/cloud_models/groq_client.py still raises ValueError the
first time a cloud call is actually attempted with no key, and main.py
already catches that. This module exists to catch it *earlier*, with a
clearer message, not to replace that.
"""

import time
from typing import Dict, Tuple

from core.logger import get_logger

logger = get_logger("ultron.startup")


def _check_config() -> Tuple[bool, str]:
    from config import GROQ_API_KEY, diagnose_env

    if GROQ_API_KEY:
        return True, "GROQ_API_KEY loaded"
    return False, diagnose_env()


def _check_storage() -> Tuple[bool, str]:
    from config import CACHE_DIR, LOGS_DIR

    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        LOGS_DIR.mkdir(parents=True, exist_ok=True)
        return True, f"{CACHE_DIR}, {LOGS_DIR}"
    except Exception as e:
        return False, str(e)


def _check_internet() -> Tuple[bool, str]:
    try:
        from core.internet_monitor import is_online

        online = is_online(force=True)
        return True, "online" if online else "offline (voice/AI will use local fallbacks)"
    except Exception as e:
        return False, str(e)


def _check_core_singletons() -> Tuple[bool, str]:
    """Touch the process-wide singletons so an init error (e.g. an
    unwritable state file) surfaces now instead of mid-conversation."""
    try:
        from core.events import get_event_bus
        from core.state_manager import get_state_manager

        get_event_bus()
        get_state_manager()
        return True, "event bus + state manager ready"
    except Exception as e:
        return False, str(e)


def _check_admin_status() -> Tuple[bool, str]:
    """Reports elevation status on every boot instead of only when the
    user thinks to ask after something already failed - see
    windows/system_info/admin.py's module docstring for why this
    matters (firewall/service/kill_process/etc. all need it, and
    nothing checked or reported this before). Instant, no I/O, so
    unlike _check_internet this stays on the fast synchronous path."""
    try:
        from windows.system_info.admin import is_admin

        elevated = is_admin()
        return True, (
            "elevated"
            if elevated
            else "not elevated - some system-control "
            "actions (firewall, services, kill_process, etc.) will fail until "
            "restarted as Administrator"
        )
    except Exception as e:
        return False, str(e)


def _check_intelligence_layer() -> Tuple[bool, str]:
    """Touch the Phase 19.1-20.6 intelligence layer singleton so its
    databases (database/*.db) are created now instead of on first use
    mid-conversation. Same "degrade, don't crash" posture as every
    other check here - intelligence_core.py already reports itself
    unavailable rather than raising if intelligence_bridge/ or the
    Phase 20.6 database layer isn't importable, so this just surfaces
    that status early instead of changing it."""
    try:
        from intelligence import get_intelligence_core

        core = get_intelligence_core()
        status = core.status()
        if not status.get("intelligence_core_available"):
            return False, "intelligence_bridge not available - running degraded/no-op"
        return True, f"{len(status.get('bridges', {}))} bridges, db={status.get('phase_20_6_database_available')}"
    except Exception as e:
        return False, str(e)


CHECKS = (
    ("config", _check_config),
    ("storage", _check_storage),
    ("core_singletons", _check_core_singletons),
    ("admin_status", _check_admin_status),
)

# Speed fix: internet and intelligence_layer used to be blocking checks
# in CHECKS, run synchronously in main.py before the assistant could
# respond to anything. Both explicitly "degrade, don't crash" already
# (see their own docstrings/comments) - Ultron works fine either way,
# they're purely informational - so neither needs to be on the
# critical boot path. _check_internet in particular used to cost up to
# len(INTERNET_CHECK_HOSTS) x INTERNET_CHECK_TIMEOUT seconds worst case
# (core/internet_monitor.py's own concurrency fix cut that further).
# Moved into core/warmup.py's existing background thread instead - same
# fire-and-forget pattern already used there for TTS/STT/pywinauto/app
# cache, just logged instead of held up for main.py's printed report.
BACKGROUND_CHECKS = (
    ("internet", _check_internet),
    ("intelligence_layer", _check_intelligence_layer),
)


def run_startup_checks(verbose: bool = True) -> Dict[str, Tuple[bool, str]]:
    """Runs every check in CHECKS and returns {name: (ok, detail)}.
    Pass verbose=False to skip the printed summary (e.g. from
    core.debug_console, which has its own prompt).

    Only the fast, essential checks (config/storage/core_singletons)
    run here now - see BACKGROUND_CHECKS above for why internet/
    intelligence_layer moved to core/warmup.py's background thread
    instead of blocking this."""
    report: Dict[str, Tuple[bool, str]] = {}
    t0 = time.time()

    for name, check in CHECKS:
        try:
            report[name] = check()
        except Exception as e:
            # A check itself misbehaving still shouldn't stop boot.
            report[name] = (False, f"check raised: {e}")

    elapsed = round(time.time() - t0, 2)
    summary = ", ".join(f"{k}={'ok' if ok else 'FAIL'}" for k, (ok, _) in report.items())
    logger.info(f"Startup checks completed in {elapsed}s: {summary}")

    if verbose:
        print_report(report)

    return report


def run_background_checks() -> Dict[str, Tuple[bool, str]]:
    """Runs BACKGROUND_CHECKS (internet, intelligence_layer) and logs
    the result - called from core/warmup.py's background thread, not
    from main.py directly, so it never blocks boot. Same never-raises
    contract as run_startup_checks()."""
    report: Dict[str, Tuple[bool, str]] = {}
    t0 = time.time()

    for name, check in BACKGROUND_CHECKS:
        try:
            report[name] = check()
        except Exception as e:
            report[name] = (False, f"check raised: {e}")

    elapsed = round(time.time() - t0, 2)
    summary = ", ".join(f"{k}={'ok' if ok else 'FAIL'}" for k, (ok, _) in report.items())
    logger.info(f"Background startup checks completed in {elapsed}s: {summary}")
    return report


def print_report(report: Dict[str, Tuple[bool, str]]) -> None:
    """Plain-text summary (no colour codes, to avoid importing main.py /
    core.assistant just for C - this module has to stay importable
    before either of those exist)."""
    print("\n[startup]")
    for name, (ok, detail) in report.items():
        status = "OK" if ok else "WARN"
        print(f"  [{status}] {name}: {detail}")
    print()
