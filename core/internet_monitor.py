"""
Internet monitor
================
Fast, cached "are we online right now" check used by ai/ai_router.py to
decide cloud vs local per turn, and by ui/dashboard for a live network
indicator.

Deliberately NOT a simple "ping google.com" on every call - that's a
network round trip on the hot path of every single user turn, which is
exactly the kind of latency the voice pipeline is trying to eliminate.
Instead:

  - A raw connectivity check opens a raw TCP socket to a well-known
    fast host:port (default 1.1.1.1:53 / 8.8.8.8:53 - DNS servers that
    always answer connects quickly, no DNS resolution needed for the
    check itself) with a short timeout. This is much faster than an
    HTTP request and doesn't depend on any particular site being up.
  - The result is cached for INTERNET_CHECK_CACHE_SECONDS so a burst of
    calls (e.g. AI router + dashboard both asking within the same
    second) only pays for one real check.
  - An optional background thread polls on the same interval and emits
    "internet_online" / "internet_offline" on the event bus only on
    actual state transitions, so subscribers (dashboard, AI router
    logging) don't get spammed every poll.
"""

import socket
import threading
import time
from typing import Optional

from config import INTERNET_CHECK_HOSTS, INTERNET_CHECK_TIMEOUT, INTERNET_CHECK_CACHE_SECONDS
from core.logger import get_logger

logger = get_logger("internet_monitor")


def _check_one_host(entry: str) -> bool:
    try:
        host, port_str = entry.rsplit(":", 1)
        port = int(port_str)
    except ValueError:
        return False
    try:
        with socket.create_connection((host, port), timeout=INTERNET_CHECK_TIMEOUT):
            return True
    except OSError:
        return False


def _raw_check() -> bool:
    """Check every configured host:port concurrently; online as soon as
    ANY one connects.

    Speed fix: this used to try hosts one at a time, so on a network
    where the first host is slow/blocked (common - some routers,
    corporate firewalls, and VPNs silently drop outbound connects to
    one DNS provider but not another) the worst case was
    len(INTERNET_CHECK_HOSTS) x INTERNET_CHECK_TIMEOUT seconds - and
    per this module's own docstring, is_online() sits on the hot path
    of every single user turn (ai/ai_router.py), cached for only
    INTERNET_CHECK_CACHE_SECONDS (4s default), so that full worst case
    could be paid again on almost every turn, not just once at startup.
    Checking hosts concurrently caps the worst case at exactly one
    timeout no matter how many hosts are configured, with the same
    result as before on every network - this only removes wasted
    sequential waiting, it never changes online/offline classification.
    """
    if len(INTERNET_CHECK_HOSTS) <= 1:
        return _check_one_host(INTERNET_CHECK_HOSTS[0]) if INTERNET_CHECK_HOSTS else False

    result = threading.Event()
    found = {"online": False}

    def _worker(entry: str):
        if _check_one_host(entry):
            found["online"] = True
            result.set()

    threads = [threading.Thread(target=_worker, args=(e,), daemon=True) for e in INTERNET_CHECK_HOSTS]
    for t in threads:
        t.start()
    # Wait for either the first success, or every thread to have had a
    # chance to finish its own timeout (worst case: one INTERNET_CHECK_TIMEOUT,
    # not one per host) - daemon=True means any thread still hung past
    # this point (shouldn't happen, socket timeout is enforced) can't
    # block process exit either.
    result.wait(timeout=INTERNET_CHECK_TIMEOUT + 0.2)
    return found["online"]


class InternetMonitor:
    """Cached connectivity checker, with an optional background poller."""

    def __init__(self):
        self._lock = threading.Lock()
        self._last_check_time: float = 0.0
        self._last_result: bool = True  # optimistic default before first check
        self._poll_thread: Optional[threading.Thread] = None
        self._stop_polling = threading.Event()

    def is_online(self, force: bool = False) -> bool:
        """Return current online status, using the cache unless `force` or
        the cache has expired."""
        now = time.monotonic()
        with self._lock:
            cache_age = now - self._last_check_time
            if not force and cache_age < INTERNET_CHECK_CACHE_SECONDS and self._last_check_time > 0:
                return self._last_result

        result = _raw_check()

        with self._lock:
            changed = self._last_check_time > 0 and result != self._last_result
            self._last_result = result
            self._last_check_time = now

        if changed:
            self._on_transition(result)

        return result

    def _on_transition(self, now_online: bool) -> None:
        logger.info("Internet connectivity changed: %s", "online" if now_online else "offline")
        try:
            from core.events import get_event_bus

            get_event_bus().emit("internet_online" if now_online else "internet_offline")
        except Exception:
            from core.error_trace import log_swallowed as _lsw

            _lsw("core.internet_monitor._on_transition")

    # -- optional background polling, for the dashboard's live status ----
    def start_background_polling(self, interval: Optional[float] = None) -> None:
        if self._poll_thread and self._poll_thread.is_alive():
            return
        self._stop_polling.clear()
        poll_interval = interval or INTERNET_CHECK_CACHE_SECONDS

        def _loop():
            while not self._stop_polling.is_set():
                self.is_online(force=True)
                self._stop_polling.wait(poll_interval)

        self._poll_thread = threading.Thread(target=_loop, daemon=True)
        self._poll_thread.start()

    def stop_background_polling(self) -> None:
        self._stop_polling.set()


_monitor: Optional[InternetMonitor] = None


def get_monitor() -> InternetMonitor:
    global _monitor
    if _monitor is None:
        _monitor = InternetMonitor()
    return _monitor


def is_online(force: bool = False) -> bool:
    """Module-level convenience - what most callers (ai/ai_router.py) use."""
    return get_monitor().is_online(force=force)
