"""
PHASE 30 - HTTP Connection Pooling & Session Management
========================================================
Optimization for tools that make repeated HTTP requests (web search, URL
reads, API calls to weather/currency/translate, etc.): instead of creating
a fresh connection for every tool call, maintain a shared requests.Session
with connection pooling, keep-alive enabled, and sensible timeouts.

Each call to get_http_session() returns the same Session object (lazy-
initialized and thread-safe), so:
  - TCP handshake cost amortized across N requests to the same domain
  - Connection kept alive via HTTP keep-alive header (~100ms saved per
    repeat request to the same host)
  - Connection pool (default 10 per pool, 10 pools) reuses sockets

This is purely internal - tool authors (phase30_new_tools.py,
phase30_advanced_tools.py, WebTools in skills/internet/, etc.) just call
requests.get(url) and all benefit from pooling. No API change needed.

Note: We DON'T cache responses here (that's ai/tool_runtime.py's job with
_CACHEABLE_TOOLS and _tool_cache for idempotent reads). This layer only
manages the connections themselves.
"""

import requests
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry
import threading
from typing import Optional

_http_session: Optional[requests.Session] = None
_http_session_lock = threading.Lock()


def get_http_session() -> requests.Session:
    """Get or create a shared requests.Session with connection pooling
    enabled. Thread-safe, returns the same Session to all callers."""
    global _http_session
    if _http_session is None:
        with _http_session_lock:
            if _http_session is None:
                _http_session = _create_http_session()
    return _http_session


def _create_http_session() -> requests.Session:
    """Create a session with connection pooling, keep-alive, and retry
    strategy for transient failures."""
    session = requests.Session()

    # Retry strategy: retry on connection errors and 5xx server errors,
    # but not 4xx (auth, not found, etc.). Backoff: exponential with
    # jitter to avoid thundering herd on API outage recovery.
    retry_strategy = Retry(
        total=2,
        backoff_factor=0.3,
        status_forcelist=[500, 502, 503, 504],
        allowed_methods=["GET", "POST"],  # only idempotent methods
    )

    # HTTPAdapter with connection pooling (10 connections per pool, 10
    # pools for different hosts = 100 concurrent connections)
    adapter = HTTPAdapter(
        max_retries=retry_strategy,
        pool_connections=10,
        pool_maxsize=10,
    )
    session.mount("http://", adapter)
    session.mount("https://", adapter)

    # Default headers to look like a browser (some endpoints reject
    # requests without User-Agent)
    session.headers.update(
        {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        }
    )

    return session
