"""
Cache Strategist (Phase 20.3 - Adaptive Performance)
==================================================
The other half of "adaptive performance" alongside path_optimizer.py:
picking the fastest provider only gets you so far when the actual
fastest call is the one you never make. This module decides whether
a given (operation, key) result is worth caching at all, holds the
cached value in memory, and adapts each operation's TTL from its own
observed hit rate rather than a single global constant - an
operation whose results are being reused heavily earns a longer TTL;
one that's mostly missing gets squeezed back down rather than left
holding memory for data nobody re-requests.

should_cache() is a cost/benefit judgment, not a correctness one:
it only says whether caching is worth the memory and staleness risk
given how expensive the call was, never whether the data is safe to
cache at all - that call belongs to the caller, who knows if a result
is deterministic/idempotent for its key. This module assumes it's
only ever asked to cache things where that's already true.

In-memory only, same posture as context_preloader.py's fetched
values in Phase 20.2: cached values themselves never touch disk, on
the reasoning that whatever they represent can always be re-fetched,
and disk persistence would risk serving stale/wrong data across a
restart when the caller has no way to know it's stale. Only
aggregate hit/miss/store metadata is persisted, for the adaptive TTL
math and for auto_optimizer.py to reason about.

Storage: database/performance_metrics.db, table cache_events (this
module's own table, shared db file with the rest of
adaptive_performance/, same pattern as predictive_preparation.db in
Phase 20.2).
"""

import sqlite3
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from core.logger import get_logger

logger = get_logger("ultron.cache_strategist")

DB_PATH = Path(__file__).resolve().parent.parent.parent / "database" / "performance_metrics.db"

_instance: Optional["CacheStrategist"] = None
_instance_lock = threading.Lock()

# only worth caching if a single call costs at least this much - a
# 20ms lookup isn't worth the staleness risk or memory
_MIN_LATENCY_MS_TO_CACHE = 150.0

_DEFAULT_TTL_SECONDS = 300.0
_MIN_TTL_SECONDS = 30.0
_MAX_TTL_SECONDS = 3600.0

# how far the adaptive TTL steps per tune_ttl() call, and the hit
# rate thresholds that decide which direction it steps
_TTL_STEP_FACTOR = 1.5
_HIT_RATE_HIGH = 0.6
_HIT_RATE_LOW = 0.2

# minimum number of get() calls in an operation's recent history
# before its hit rate is trusted enough to adjust TTL from - avoids
# over-reacting to the first couple of lookups
_MIN_SAMPLES_TO_TUNE = 10


class CacheStrategist:
    """should_cache() to decide, get()/set() to use the in-memory
    cache, tune_ttl() to adapt an operation's TTL from its hit rate."""

    def __init__(self, db_path: Path = DB_PATH):
        self._db_path = db_path
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
        self._conn.execute("""CREATE TABLE IF NOT EXISTS cache_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                operation TEXT,
                cache_key TEXT,
                event TEXT,
                timestamp REAL
            )""")
        self._conn.commit()

        # (operation, key) -> (value, expires_at)
        self._store: Dict[Tuple[str, str], Tuple[Any, float]] = {}
        # per-operation current TTL, adapted over time by tune_ttl()
        self._ttl_seconds: Dict[str, float] = {}

    def should_cache(self, operation: str, latency_ms: float) -> Dict:
        if latency_ms < _MIN_LATENCY_MS_TO_CACHE:
            return {
                "cache": False,
                "reason": f"latency {latency_ms:.0f}ms below "
                f"{_MIN_LATENCY_MS_TO_CACHE:.0f}ms threshold - not worth caching",
            }
        return {
            "cache": True,
            "reason": f"latency {latency_ms:.0f}ms clears "
            f"{_MIN_LATENCY_MS_TO_CACHE:.0f}ms threshold - worth caching",
        }

    def get(self, operation: str, key: str) -> Dict:
        now = time.time()
        cache_key = (operation, key)
        with self._lock:
            entry = self._store.get(cache_key)
            if entry is not None and entry[1] > now:
                value = entry[0]
                hit = True
            else:
                if entry is not None:
                    del self._store[cache_key]
                value = None
                hit = False
        self._log_event(operation, key, "hit" if hit else "miss")
        return {"hit": hit, "value": value}

    def set(self, operation: str, key: str, value: Any, ttl_seconds: Optional[float] = None) -> Dict:
        with self._lock:
            ttl = ttl_seconds if ttl_seconds is not None else self._ttl_seconds.get(operation, _DEFAULT_TTL_SECONDS)
            expires_at = time.time() + ttl
            self._store[(operation, key)] = (value, expires_at)
        self._log_event(operation, key, "store")
        return {"operation": operation, "key": key, "ttl_seconds": ttl, "expires_at": expires_at}

    def invalidate(self, operation: str, key: Optional[str] = None) -> int:
        removed = 0
        with self._lock:
            if key is not None:
                if (operation, key) in self._store:
                    del self._store[(operation, key)]
                    removed = 1
            else:
                to_remove = [k for k in self._store if k[0] == operation]
                for k in to_remove:
                    del self._store[k]
                removed = len(to_remove)
        return removed

    def get_hit_rate(self, operation: str, window_seconds: float = 3600.0) -> Optional[float]:
        with self._lock:
            rows = self._conn.execute(
                """SELECT event FROM cache_events
                   WHERE operation = ? AND event IN ('hit', 'miss') AND timestamp >= ?""",
                (operation, time.time() - window_seconds),
            ).fetchall()
        if not rows:
            return None
        hits = sum(1 for (e,) in rows if e == "hit")
        return round(hits / len(rows), 4)

    def tune_ttl(self, operation: str, window_seconds: float = 3600.0) -> Dict:
        with self._lock:
            rows = self._conn.execute(
                """SELECT event FROM cache_events
                   WHERE operation = ? AND event IN ('hit', 'miss') AND timestamp >= ?""",
                (operation, time.time() - window_seconds),
            ).fetchall()
            current_ttl = self._ttl_seconds.get(operation, _DEFAULT_TTL_SECONDS)

        sample_count = len(rows)
        if sample_count < _MIN_SAMPLES_TO_TUNE:
            return {
                "operation": operation,
                "ttl_seconds": current_ttl,
                "hit_rate": None,
                "adjusted": False,
                "reason": f"only {sample_count} sample(s), need " f"{_MIN_SAMPLES_TO_TUNE} before tuning",
            }

        hits = sum(1 for (e,) in rows if e == "hit")
        hit_rate = hits / sample_count

        if hit_rate >= _HIT_RATE_HIGH:
            new_ttl = min(_MAX_TTL_SECONDS, current_ttl * _TTL_STEP_FACTOR)
            reason = f"hit_rate {hit_rate:.2f} >= {_HIT_RATE_HIGH:.2f} - extending TTL"
        elif hit_rate <= _HIT_RATE_LOW:
            new_ttl = max(_MIN_TTL_SECONDS, current_ttl / _TTL_STEP_FACTOR)
            reason = f"hit_rate {hit_rate:.2f} <= {_HIT_RATE_LOW:.2f} - shrinking TTL"
        else:
            new_ttl = current_ttl
            reason = f"hit_rate {hit_rate:.2f} within normal range - leaving TTL unchanged"

        with self._lock:
            self._ttl_seconds[operation] = new_ttl

        adjusted = new_ttl != current_ttl
        if adjusted:
            logger.info(f"cache_strategist: '{operation}' TTL {current_ttl:.0f}s -> {new_ttl:.0f}s ({reason})")
        return {
            "operation": operation,
            "ttl_seconds": round(new_ttl, 1),
            "hit_rate": round(hit_rate, 4),
            "adjusted": adjusted,
            "reason": reason,
        }

    def get_current_ttl(self, operation: str) -> float:
        with self._lock:
            return self._ttl_seconds.get(operation, _DEFAULT_TTL_SECONDS)

    def get_recent_events(self, operation: Optional[str] = None, limit: int = 20) -> List[Dict]:
        with self._lock:
            if operation:
                rows = self._conn.execute(
                    """SELECT operation, cache_key, event, timestamp FROM cache_events
                       WHERE operation = ? ORDER BY id DESC LIMIT ?""",
                    (operation, limit),
                ).fetchall()
            else:
                rows = self._conn.execute(
                    """SELECT operation, cache_key, event, timestamp FROM cache_events
                       ORDER BY id DESC LIMIT ?""",
                    (limit,),
                ).fetchall()
        return [{"operation": o, "key": k, "event": e, "timestamp": ts} for o, k, e, ts in rows]

    def _log_event(self, operation: str, key: str, event: str) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO cache_events (operation, cache_key, event, timestamp) VALUES (?, ?, ?, ?)",
                (operation, key, event, time.time()),
            )
            self._conn.commit()


def get_cache_strategist() -> CacheStrategist:
    """Process-wide CacheStrategist singleton."""
    global _instance
    if _instance is None:
        with _instance_lock:
            if _instance is None:
                _instance = CacheStrategist()
    return _instance
