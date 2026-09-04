"""
Context Preloader (Phase 20.2 - Predictive Preparation)
==================================================
Given a predicted next task, proactively runs whichever data
providers that task is known to need - today's calendar, the current
project's recent files, system status, whatever a caller registers -
so the data is already sitting in an in-memory cache by the time the
task actually starts, instead of being fetched cold at the moment
it's needed.

Purely a scheduling layer: this module never fetches anything itself.
register_provider() takes a plain no-argument callable supplied by
whichever module actually owns that data (calendar skill, filesystem
skill, etc) - context_preloader.py just decides *when* to call it,
gated by resource_optimizer.py and a per-key TTL so the same context
isn't refetched every time a prediction happens to name it again.

Privacy note, same "local-only storage / sensitive content filtering"
posture as the SECURITY module (Phase 18.8): only cache *metadata*
(key, status, timestamp) is ever written to the database. The actual
fetched values live in the in-memory cache only, for this process's
lifetime - calendar contents, file contents, etc. never touch disk
through this module.

Storage: database/predictive_preparation.db, table
context_preload_log (metadata only, see above).
"""

import sqlite3
import threading
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from core.logger import get_logger
from intelligence.predictive_preparation.resource_optimizer import (
    get_resource_optimizer,
    KIND_CONTEXT,
    COST_LOW,
)

logger = get_logger("ultron.context_preloader")

DB_PATH = Path(__file__).resolve().parent.parent.parent / "database" / "predictive_preparation.db"

_instance: Optional["ContextPreloader"] = None
_instance_lock = threading.Lock()

_DEFAULT_TTL_SECONDS = 300.0


class ContextPreloader:
    """register_provider()/register_task_context_mapping() to
    configure; preload_for_task() to act on a prediction; get_cached()
    to read whatever's been prefetched."""

    def __init__(self, db_path: Path = DB_PATH):
        self._db_path = db_path
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
        self._conn.execute("""CREATE TABLE IF NOT EXISTS context_preload_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                context_key TEXT,
                task_type TEXT,
                confidence REAL,
                status TEXT,
                reason TEXT,
                timestamp REAL
            )""")
        self._conn.commit()

        self._resource = get_resource_optimizer()
        self._providers: Dict[str, Dict] = {}
        self._task_map: Dict[str, List[str]] = {}
        # in-memory only - actual fetched values never go to disk
        self._cache: Dict[str, Dict] = {}

    def register_provider(
        self, context_key: str, provider_fn: Callable[[], Any], ttl_seconds: float = _DEFAULT_TTL_SECONDS
    ) -> None:
        with self._lock:
            self._providers[context_key] = {"fn": provider_fn, "ttl": ttl_seconds}
        logger.info(f"context_preloader: registered provider for '{context_key}' (ttl={ttl_seconds:.0f}s)")

    def register_task_context_mapping(self, task_type: str, context_keys: List[str]) -> None:
        with self._lock:
            self._task_map[task_type] = list(context_keys)

    def preload_for_task(self, task_type: str, confidence: float, context: Optional[Dict] = None) -> Dict:
        with self._lock:
            keys = list(self._task_map.get(task_type, []))

        if not keys:
            return {
                "attempted": False,
                "reasons": [f"no context mapping registered for task_type '{task_type}'"],
                "results": [],
            }

        results = [self._preload_one(key, task_type, confidence, context) for key in keys]
        return {"attempted": True, "reasons": [], "results": results}

    def get_cached(self, context_key: str) -> Optional[Dict]:
        with self._lock:
            entry = self._cache.get(context_key)
            provider = self._providers.get(context_key)
        if entry is None:
            return None
        ttl = provider["ttl"] if provider else _DEFAULT_TTL_SECONDS
        stale = (time.time() - entry["fetched_at"]) >= ttl
        return {"value": entry["value"], "fetched_at": entry["fetched_at"], "stale": stale}

    def get_recent_log(self, limit: int = 20) -> List[Dict]:
        with self._lock:
            rows = self._conn.execute(
                """SELECT context_key, task_type, confidence, status, reason, timestamp
                   FROM context_preload_log ORDER BY id DESC LIMIT ?""",
                (limit,),
            ).fetchall()
        return [
            {"context_key": k, "task_type": t, "confidence": c, "status": s, "reason": r, "timestamp": ts}
            for k, t, c, s, r, ts in rows
        ]

    def _preload_one(self, context_key: str, task_type: str, confidence: float, context: Optional[Dict]) -> Dict:
        with self._lock:
            provider = self._providers.get(context_key)

        if provider is None:
            return self._log_and_return(
                context_key, task_type, confidence, "skipped", "no provider registered for this context key"
            )

        cached = self.get_cached(context_key)
        if cached is not None and not cached["stale"]:
            return self._log_and_return(context_key, task_type, confidence, "skipped", "already fresh in cache")

        decision = self._resource.check(KIND_CONTEXT, cost=COST_LOW, context=context)
        if not decision["allowed"]:
            reason = "; ".join(decision["reasons"]) or "resource_optimizer denied"
            return self._log_and_return(context_key, task_type, confidence, "skipped", reason)

        try:
            value = provider["fn"]()
        except Exception as e:
            logger.warning(f"context_preloader: provider for '{context_key}' raised: {e}")
            return self._log_and_return(context_key, task_type, confidence, "failed", str(e))

        with self._lock:
            self._cache[context_key] = {"value": value, "fetched_at": time.time()}
        self._resource.register_spend(KIND_CONTEXT)
        logger.info(f"context_preloader: prefetched '{context_key}' for predicted task '{task_type}'")
        return self._log_and_return(context_key, task_type, confidence, "prefetched", "provider ran successfully")

    def _log_and_return(self, context_key: str, task_type: str, confidence: float, status: str, reason: str) -> Dict:
        now = time.time()
        with self._lock:
            self._conn.execute(
                """INSERT INTO context_preload_log (context_key, task_type, confidence, status, reason, timestamp)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (context_key, task_type, confidence, status, reason, now),
            )
            self._conn.commit()
        return {
            "context_key": context_key,
            "task_type": task_type,
            "confidence": confidence,
            "status": status,
            "reason": reason,
            "timestamp": now,
        }


def get_context_preloader() -> ContextPreloader:
    """Process-wide ContextPreloader singleton."""
    global _instance
    if _instance is None:
        with _instance_lock:
            if _instance is None:
                _instance = ContextPreloader()
    return _instance
