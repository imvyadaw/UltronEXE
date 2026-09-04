"""
Model Preloader (Phase 20.2 - Predictive Preparation)
==================================================
Given a predicted next task, warms whichever local model that task's
category is known to need - a zero-token generate call against the
local model server with keep_alive set, so the model is already
resident in memory by the time the AI routing layer actually needs
it. Targets the same local model server as the rest of this build's
offline fallback path (Ollama on 127.0.0.1 - this module uses
127.0.0.1 explicitly for the same reason the earlier localhost/
127.0.0.1 offline-fallback bug got fixed elsewhere in this project:
some Windows configurations resolve "localhost" inconsistently).

is_warm() prefers asking the model server directly which models are
currently loaded (Ollama's /api/ps) over trusting an in-memory
timestamp, since the server's own keep_alive expiry is the actual
source of truth - the TTL heuristic is only a fallback for when the
server can't be reached at all, same "degrade gracefully instead of
guessing wrong" posture as resource_optimizer.py's psutil guard.

Whitelist-only via register_model_mapping(), same posture as
app_preloader.py's registry - Phase 20.2 ships this with nothing
registered. Every preload_for_task() call runs through
resource_optimizer.py first and every attempt is logged regardless of
outcome.

Storage: database/predictive_preparation.db, table model_warm_log.
"""

import json
import sqlite3
import threading
import time
import urllib.request
import urllib.error
from pathlib import Path
from typing import Dict, List, Optional

from core.logger import get_logger
from intelligence.predictive_preparation.resource_optimizer import (
    get_resource_optimizer,
    KIND_MODEL,
    COST_MEDIUM,
)

logger = get_logger("ultron.model_preloader")

DB_PATH = Path(__file__).resolve().parent.parent.parent / "database" / "predictive_preparation.db"

_instance: Optional["ModelPreloader"] = None
_instance_lock = threading.Lock()

_DEFAULT_HOST = "http://127.0.0.1:11434"
_DEFAULT_MIN_CONFIDENCE = 0.5
_DEFAULT_COOLDOWN_SECONDS = 300.0
_DEFAULT_KEEP_ALIVE = "5m"
_REQUEST_TIMEOUT_SECONDS = 10.0

# fallback-only: assumed warm duration when the server can't be asked
# directly via /api/ps, matches _DEFAULT_KEEP_ALIVE above
_WARM_TTL_FALLBACK_SECONDS = 300.0


class ModelPreloader:
    """register_model_mapping() to configure; preload_for_task() to
    act on a prediction; is_warm() to check current state."""

    def __init__(self, db_path: Path = DB_PATH, host: str = _DEFAULT_HOST):
        self._db_path = db_path
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._host = host
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
        self._conn.execute("""CREATE TABLE IF NOT EXISTS model_warm_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                model_name TEXT,
                task_type TEXT,
                confidence REAL,
                status TEXT,
                reason TEXT,
                latency_ms REAL,
                timestamp REAL
            )""")
        self._conn.commit()

        self._resource = get_resource_optimizer()
        self._registry: Dict[str, str] = {}
        self._model_cfg: Dict[str, Dict] = {}
        self._last_warm_ts: Dict[str, float] = {}

    def register_model_mapping(
        self,
        task_type_or_category: str,
        model_name: str,
        min_confidence: float = _DEFAULT_MIN_CONFIDENCE,
        cooldown_seconds: float = _DEFAULT_COOLDOWN_SECONDS,
    ) -> None:
        with self._lock:
            self._registry[task_type_or_category] = model_name
            self._model_cfg.setdefault(
                model_name,
                {
                    "min_confidence": min_confidence,
                    "cooldown_seconds": cooldown_seconds,
                },
            )
        logger.info(f"model_preloader: registered '{task_type_or_category}' -> model '{model_name}'")

    def preload_for_task(self, task_type_or_category: str, confidence: float, context: Optional[Dict] = None) -> Dict:
        with self._lock:
            model_name = self._registry.get(task_type_or_category)
            cfg = self._model_cfg.get(model_name) if model_name else None

        if model_name is None:
            return self._log_and_return(
                None,
                task_type_or_category,
                confidence,
                "skipped",
                f"no model mapping registered for '{task_type_or_category}'",
                None,
            )

        if confidence < cfg["min_confidence"]:
            return self._log_and_return(
                model_name,
                task_type_or_category,
                confidence,
                "skipped",
                f"confidence {confidence:.2f} below threshold {cfg['min_confidence']:.2f}",
                None,
            )

        now = time.time()
        with self._lock:
            last = self._last_warm_ts.get(model_name)
        if last is not None and (now - last) < cfg["cooldown_seconds"]:
            remaining = cfg["cooldown_seconds"] - (now - last)
            return self._log_and_return(
                model_name,
                task_type_or_category,
                confidence,
                "skipped",
                f"cooldown active, {remaining:.0f}s remaining",
                None,
            )

        if self.is_warm(model_name):
            return self._log_and_return(
                model_name, task_type_or_category, confidence, "skipped", "model already warm", None
            )

        decision = self._resource.check(KIND_MODEL, cost=COST_MEDIUM, context=context)
        if not decision["allowed"]:
            reason = "; ".join(decision["reasons"]) or "resource_optimizer denied"
            return self._log_and_return(model_name, task_type_or_category, confidence, "skipped", reason, None)

        start = time.time()
        try:
            self._warm_up(model_name)
        except Exception as e:
            logger.warning(
                f"model_preloader: failed to warm '{model_name}' - is the local model server running "
                f"at {self._host}? ({e})"
            )
            return self._log_and_return(model_name, task_type_or_category, confidence, "failed", str(e), None)
        latency_ms = (time.time() - start) * 1000.0

        with self._lock:
            self._last_warm_ts[model_name] = now
        self._resource.register_spend(KIND_MODEL)
        logger.info(
            f"model_preloader: warmed '{model_name}' for predicted task '{task_type_or_category}' "
            f"in {latency_ms:.0f}ms"
        )
        return self._log_and_return(
            model_name, task_type_or_category, confidence, "warmed", "keep_alive warm-up sent", latency_ms
        )

    def is_warm(self, model_name: str) -> bool:
        loaded = self._loaded_models()
        if loaded is not None:
            return model_name in loaded
        with self._lock:
            last = self._last_warm_ts.get(model_name)
        return last is not None and (time.time() - last) < _WARM_TTL_FALLBACK_SECONDS

    def get_recent_warm_ups(self, limit: int = 20) -> List[Dict]:
        with self._lock:
            rows = self._conn.execute(
                """SELECT model_name, task_type, confidence, status, reason, latency_ms, timestamp
                   FROM model_warm_log ORDER BY id DESC LIMIT ?""",
                (limit,),
            ).fetchall()
        return [
            {
                "model_name": m,
                "task_type": t,
                "confidence": c,
                "status": s,
                "reason": r,
                "latency_ms": lat,
                "timestamp": ts,
            }
            for m, t, c, s, r, lat, ts in rows
        ]

    def _warm_up(self, model_name: str) -> None:
        body = json.dumps({"model": model_name, "prompt": "", "keep_alive": _DEFAULT_KEEP_ALIVE}).encode("utf-8")
        req = urllib.request.Request(
            f"{self._host}/api/generate",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=_REQUEST_TIMEOUT_SECONDS) as resp:
            resp.read()

    def _loaded_models(self) -> Optional[set]:
        try:
            req = urllib.request.Request(f"{self._host}/api/ps", method="GET")
            with urllib.request.urlopen(req, timeout=_REQUEST_TIMEOUT_SECONDS) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            return {m.get("name") or m.get("model") for m in data.get("models", [])}
        except (urllib.error.URLError, TimeoutError, ValueError, OSError) as e:
            logger.debug(f"model_preloader: could not query loaded models from {self._host}: {e}")
            return None

    def _log_and_return(
        self,
        model_name: Optional[str],
        task_type: str,
        confidence: float,
        status: str,
        reason: str,
        latency_ms: Optional[float],
    ) -> Dict:
        now = time.time()
        with self._lock:
            self._conn.execute(
                """INSERT INTO model_warm_log
                   (model_name, task_type, confidence, status, reason, latency_ms, timestamp)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (model_name, task_type, confidence, status, reason, latency_ms, now),
            )
            self._conn.commit()
        return {
            "model_name": model_name,
            "task_type": task_type,
            "confidence": confidence,
            "status": status,
            "reason": reason,
            "latency_ms": latency_ms,
            "timestamp": now,
        }


def get_model_preloader() -> ModelPreloader:
    """Process-wide ModelPreloader singleton."""
    global _instance
    if _instance is None:
        with _instance_lock:
            if _instance is None:
                _instance = ModelPreloader()
    return _instance
