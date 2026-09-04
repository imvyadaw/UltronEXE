"""
Performance Engine (Phase 20.3 - Adaptive Performance)
==================================================
Single entry point for the adaptive_performance/ package - mirrors
predictive_engine.py's role in Phase 20.2 (a thin orchestrator over
otherwise-independent sub-modules that still work fine called
directly). Two calls are all a caller needs around an actual provider
call:

    plan_call()   - before making the call: check
                    cache_strategist.py for a cached result, and if
                    it's a miss, ask path_optimizer.py which provider
                    to use.
    record_call() - after the call finishes: log the outcome to
                    latency_tracker.py (which everything else in this
                    package derives from) and, if it was a cache miss
                    worth caching, store the result via
                    cache_strategist.py.

Pipeline per plan_call():

    cache_strategist.py -> cache hit? return it, skip path_optimizer.py entirely
                         -> cache miss -> path_optimizer.py -> provider_analyzer.py
                            (scores) -> latency_tracker.py (raw data the score
                            came from)

Pipeline per record_call():

    latency_tracker.py  -> log the outcome (always)
    cache_strategist.py -> should_cache() + set(), only if this call
                            was a cache miss and the result is worth
                            keeping

auto_optimizer.py is not called from either pipeline - it runs on its
own schedule (or a caller's), sweeping registered operations rather
than reacting to any single call. register_operation() below wires an
operation into path_optimizer.py's candidate list and
auto_optimizer.py's sweep list in one call, since in practice both are
set up together.

Storage: database/performance_metrics.db, table performance_events
(this module's own table, logging the full pipeline outcome per
plan_call()/record_call() pair; latency_tracker.py/provider_analyzer.py/
path_optimizer.py/cache_strategist.py/auto_optimizer.py each keep
their own tables in the same database file).

Purely additive - nothing in Phase 1-20 imports from here, and this
module does not import from predictive_preparation/ (Phase 20.2) or
proactive_intelligence/ (Phase 20.1). All three solve different
problems (what to say / what to have ready / how to make a call fast)
and can be wired together by a caller that wants more than one, but
none depends on another.
"""

import sqlite3
import threading
import time
import uuid
from pathlib import Path
from typing import Dict, List, Optional

from core.logger import get_logger
from intelligence.adaptive_performance.latency_tracker import get_latency_tracker
from intelligence.adaptive_performance.provider_analyzer import get_provider_analyzer
from intelligence.adaptive_performance.path_optimizer import get_path_optimizer
from intelligence.adaptive_performance.cache_strategist import get_cache_strategist
from intelligence.adaptive_performance.auto_optimizer import get_auto_optimizer

logger = get_logger("ultron.performance_engine")

DB_PATH = Path(__file__).resolve().parent.parent.parent / "database" / "performance_metrics.db"

_instance: Optional["PerformanceEngine"] = None
_instance_lock = threading.Lock()


class PerformanceEngine:
    """Orchestrates latency_tracker / provider_analyzer /
    path_optimizer / cache_strategist / auto_optimizer into the two
    calls a caller needs: plan_call() and record_call()."""

    def __init__(self, db_path: Path = DB_PATH):
        self._db_path = db_path
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
        self._conn.execute("""CREATE TABLE IF NOT EXISTS performance_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                call_id TEXT,
                operation TEXT,
                provider TEXT,
                cache_status TEXT,
                latency_ms REAL,
                success INTEGER,
                timestamp REAL
            )""")
        self._conn.commit()

        self._latency = get_latency_tracker()
        self._analyzer = get_provider_analyzer()
        self._paths = get_path_optimizer()
        self._cache = get_cache_strategist()
        self._auto = get_auto_optimizer()

    def register_operation(self, operation: str, providers: List[str]) -> None:
        """One-time setup: tells path_optimizer.py the candidates for
        this operation and tells auto_optimizer.py to keep sweeping
        it. Empty by default for both - a caller elsewhere in ULTRON
        owns this decision, same as app_preloader.py's registry."""
        self._paths.register_operation_providers(operation, providers)
        self._auto.register_operation(operation)

    def plan_call(self, operation: str, cache_key: Optional[str] = None, context: Optional[Dict] = None) -> Dict:
        """Call before making a provider call. Returns a cached value
        if one's available (call_id will still be set so record_call()
        can log against it, but the caller should skip the real call
        entirely on a cache hit); otherwise names the provider to use."""
        call_id = str(uuid.uuid4())

        if cache_key is not None:
            cached = self._cache.get(operation, cache_key)
            if cached["hit"]:
                self._log_event(call_id, operation, provider=None, cache_status="hit", latency_ms=None, success=None)
                return {
                    "call_id": call_id,
                    "cache_hit": True,
                    "value": cached["value"],
                    "provider": None,
                    "fallback_order": [],
                    "reasons": ["served from cache"],
                }

        decision = self._paths.choose_path(operation, context=context)
        cache_status = "miss" if cache_key is not None else "not_applicable"
        return {
            "call_id": call_id,
            "cache_hit": False,
            "value": None,
            "provider": decision["provider"],
            "fallback_order": decision["fallback_order"],
            "reasons": decision["reasons"],
            "cache_status": cache_status,
        }

    def record_call(
        self,
        call_id: str,
        operation: str,
        provider: str,
        latency_ms: float,
        success: bool = True,
        error: Optional[str] = None,
        cache_key: Optional[str] = None,
        value: Optional[object] = None,
    ) -> Dict:
        """Call after a real provider call finishes (skip for calls
        served entirely from cache - plan_call() already logged
        those). Always records to latency_tracker.py; stores to
        cache_strategist.py only if cache_key/value were given and
        the call is judged worth caching."""
        self._latency.record(provider, operation, latency_ms, success=success, error=error)

        cached = False
        cache_reason = "no cache_key/value given - nothing to cache"
        if success and cache_key is not None and value is not None:
            decision = self._cache.should_cache(operation, latency_ms)
            cache_reason = decision["reason"]
            if decision["cache"]:
                self._cache.set(operation, cache_key, value)
                cached = True

        self._log_event(call_id, operation, provider, "stored" if cached else "not_stored", latency_ms, success)

        return {"call_id": call_id, "cached": cached, "cache_reason": cache_reason}

    def get_operation_summary(self, operation: str) -> Dict:
        providers = self._latency.get_providers(operation=operation)
        ranked = self._analyzer.rank_providers(providers, operation=operation) if providers else []
        return {
            "operation": operation,
            "providers": ranked,
            "hit_rate": self._cache.get_hit_rate(operation),
            "current_ttl_seconds": self._cache.get_current_ttl(operation),
            "recent_decisions": self._paths.get_recent_decisions(operation=operation, limit=5),
        }

    def get_recent_events(self, operation: Optional[str] = None, limit: int = 20) -> List[Dict]:
        with self._lock:
            if operation:
                rows = self._conn.execute(
                    """SELECT call_id, operation, provider, cache_status, latency_ms, success, timestamp
                       FROM performance_events WHERE operation = ? ORDER BY id DESC LIMIT ?""",
                    (operation, limit),
                ).fetchall()
            else:
                rows = self._conn.execute(
                    """SELECT call_id, operation, provider, cache_status, latency_ms, success, timestamp
                       FROM performance_events ORDER BY id DESC LIMIT ?""",
                    (limit,),
                ).fetchall()
        return [
            {
                "call_id": cid,
                "operation": op,
                "provider": p,
                "cache_status": cs,
                "latency_ms": lat,
                "success": bool(ok) if ok is not None else None,
                "timestamp": ts,
            }
            for cid, op, p, cs, lat, ok, ts in rows
        ]

    def _log_event(
        self,
        call_id: str,
        operation: str,
        provider: Optional[str],
        cache_status: str,
        latency_ms: Optional[float],
        success: Optional[bool],
    ) -> None:
        with self._lock:
            self._conn.execute(
                """INSERT INTO performance_events
                   (call_id, operation, provider, cache_status, latency_ms, success, timestamp)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    call_id,
                    operation,
                    provider,
                    cache_status,
                    latency_ms,
                    None if success is None else (1 if success else 0),
                    time.time(),
                ),
            )
            self._conn.commit()


def get_performance_engine() -> PerformanceEngine:
    """Process-wide PerformanceEngine singleton."""
    global _instance
    if _instance is None:
        with _instance_lock:
            if _instance is None:
                _instance = PerformanceEngine()
    return _instance
