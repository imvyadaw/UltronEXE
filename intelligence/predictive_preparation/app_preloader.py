"""
App Preloader (Phase 20.2 - Predictive Preparation)
==================================================
Given a predicted next task, silently warms whichever app that task
is known to need - launched minimized and without stealing focus -
so that when the user actually asks for it, app control (Phase 1-3's
app-launch tooling) finds it already running instead of paying a
cold-start.

Whitelist-only, same posture as user_disruption_guard.py's DND/quiet
hours being opt-in rather than assumed: nothing is preloaded unless
both the app itself (register_app) and the task->app mapping
(register_task_app_mapping) were explicitly registered by a caller.
Phase 20.2 ships this module with an empty registry - it does not
guess at installed apps or wire in any mapping itself, in keeping
with "purely additive". A caller elsewhere in ULTRON (app control,
a setup/config module) is expected to populate the registry once at
startup.

Every preload_for_task() call runs through resource_optimizer.py
first - a predicted task never causes a launch if the system doesn't
currently have room for one - and every attempt, allowed or not, is
logged so a caller can audit what got preloaded and why.

Windows-only launch path (subprocess.STARTUPINFO / SW_SHOWMINNOACTIVE)
guarded behind an os.name check, same "optional-dependency, degrade
gracefully" posture as resource_optimizer.py's psutil guard - on any
other platform this module still tracks registrations and logs
attempts, it just never actually launches anything.

Storage: database/predictive_preparation.db, table preload_log
(shared db file with the rest of predictive_preparation/, each module
owning its own table - same pattern as proactive_intelligence/'s
shared proactive_intelligence.db).
"""

import os
import subprocess
import sqlite3
import threading
import time
from pathlib import Path
from typing import Dict, List, Optional

from core.logger import get_logger
from intelligence.predictive_preparation.resource_optimizer import (
    get_resource_optimizer,
    KIND_APP,
    COST_MEDIUM,
)

logger = get_logger("ultron.app_preloader")

DB_PATH = Path(__file__).resolve().parent.parent.parent / "database" / "predictive_preparation.db"

_instance: Optional["AppPreloader"] = None
_instance_lock = threading.Lock()

_DEFAULT_MIN_CONFIDENCE = 0.5
_DEFAULT_COOLDOWN_SECONDS = 1800.0

# Windows "show minimized, don't activate" - avoids stealing focus
# from whatever the user is currently doing
_SW_SHOWMINNOACTIVE = 7


class AppPreloader:
    """register_app()/register_task_app_mapping() to configure;
    preload_for_task() to act on a prediction."""

    def __init__(self, db_path: Path = DB_PATH):
        self._db_path = db_path
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
        self._conn.execute("""CREATE TABLE IF NOT EXISTS preload_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                app_name TEXT,
                task_type TEXT,
                confidence REAL,
                status TEXT,
                reason TEXT,
                timestamp REAL
            )""")
        self._conn.commit()

        self._resource = get_resource_optimizer()
        self._registry: Dict[str, Dict] = {}
        self._task_map: Dict[str, List[str]] = {}
        self._last_preload_ts: Dict[str, float] = {}

    def register_app(
        self,
        app_name: str,
        launch_path: str,
        min_confidence: float = _DEFAULT_MIN_CONFIDENCE,
        cooldown_seconds: float = _DEFAULT_COOLDOWN_SECONDS,
    ) -> None:
        with self._lock:
            self._registry[app_name] = {
                "launch_path": launch_path,
                "min_confidence": min_confidence,
                "cooldown_seconds": cooldown_seconds,
            }
        logger.info(f"app_preloader: registered '{app_name}' -> {launch_path}")

    def register_task_app_mapping(self, task_type: str, app_names: List[str]) -> None:
        with self._lock:
            self._task_map[task_type] = list(app_names)

    def preload_for_task(self, task_type: str, confidence: float, context: Optional[Dict] = None) -> Dict:
        with self._lock:
            app_names = list(self._task_map.get(task_type, []))

        if not app_names:
            return {
                "attempted": False,
                "reasons": [f"no app mapping registered for task_type '{task_type}'"],
                "results": [],
            }

        results = []
        for app_name in app_names:
            result = self._preload_one(app_name, task_type, confidence, context)
            results.append(result)
        return {"attempted": True, "reasons": [], "results": results}

    def get_recent_preloads(self, limit: int = 20) -> List[Dict]:
        with self._lock:
            rows = self._conn.execute(
                """SELECT app_name, task_type, confidence, status, reason, timestamp
                   FROM preload_log ORDER BY id DESC LIMIT ?""",
                (limit,),
            ).fetchall()
        return [
            {"app_name": a, "task_type": t, "confidence": c, "status": s, "reason": r, "timestamp": ts}
            for a, t, c, s, r, ts in rows
        ]

    def _preload_one(self, app_name: str, task_type: str, confidence: float, context: Optional[Dict]) -> Dict:
        with self._lock:
            cfg = self._registry.get(app_name)

        if cfg is None:
            return self._log_and_return(app_name, task_type, confidence, "skipped", "app not registered/whitelisted")

        if confidence < cfg["min_confidence"]:
            return self._log_and_return(
                app_name,
                task_type,
                confidence,
                "skipped",
                f"confidence {confidence:.2f} below threshold {cfg['min_confidence']:.2f}",
            )

        now = time.time()
        with self._lock:
            last = self._last_preload_ts.get(app_name)
        if last is not None and (now - last) < cfg["cooldown_seconds"]:
            remaining = cfg["cooldown_seconds"] - (now - last)
            return self._log_and_return(
                app_name, task_type, confidence, "skipped", f"cooldown active, {remaining:.0f}s remaining"
            )

        decision = self._resource.check(KIND_APP, cost=COST_MEDIUM, context=context)
        if not decision["allowed"]:
            reason = "; ".join(decision["reasons"]) or "resource_optimizer denied"
            return self._log_and_return(app_name, task_type, confidence, "skipped", reason)

        if os.name != "nt":
            return self._log_and_return(
                app_name, task_type, confidence, "skipped", "app preloading only supported on Windows in this build"
            )

        try:
            self._launch_minimized(cfg["launch_path"])
        except Exception as e:
            logger.warning(f"app_preloader: failed to preload '{app_name}': {e}")
            return self._log_and_return(app_name, task_type, confidence, "failed", str(e))

        with self._lock:
            self._last_preload_ts[app_name] = now
        self._resource.register_spend(KIND_APP)
        logger.info(f"app_preloader: preloaded '{app_name}' for predicted task '{task_type}'")
        return self._log_and_return(app_name, task_type, confidence, "preloaded", "launched minimized")

    @staticmethod
    def _launch_minimized(launch_path: str) -> None:
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = _SW_SHOWMINNOACTIVE
        subprocess.Popen([launch_path], startupinfo=startupinfo)

    def _log_and_return(self, app_name: str, task_type: str, confidence: float, status: str, reason: str) -> Dict:
        now = time.time()
        with self._lock:
            self._conn.execute(
                """INSERT INTO preload_log (app_name, task_type, confidence, status, reason, timestamp)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (app_name, task_type, confidence, status, reason, now),
            )
            self._conn.commit()
        return {
            "app_name": app_name,
            "task_type": task_type,
            "confidence": confidence,
            "status": status,
            "reason": reason,
            "timestamp": now,
        }


def get_app_preloader() -> AppPreloader:
    """Process-wide AppPreloader singleton."""
    global _instance
    if _instance is None:
        with _instance_lock:
            if _instance is None:
                _instance = AppPreloader()
    return _instance
