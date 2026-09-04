"""
App Launch Executor (Phase 24 - Execution)
==================================================
Execution-layer wrapper around skills/app_control/app_launcher.py's
AppLauncher - this module does not reimplement app launching (that
logic - shortcut/App-Paths-registry/Appx resolution, admin-elevated
launch, launch-and-wait-for-window - already lives there and in
windows/apps/manager.py). What this module adds is the thing nothing
in Phase 1-18 had: every launch attempt is logged (own table
`app_launch_events`) so auto_player.py/web_automator.py's sibling
macro_executor.py can build a step history, and self_healer.py has
something to retry against.

launch()/launch_and_wait()/relaunch() all return the same dict the
wrapped AppLauncher call returns, with a `logged` key confirming the
attempt was recorded - callers that only want the original behavior
can ignore that key entirely.

Storage: database/execution.db, table app_launch_events (this
module's own table; auto_player.py/web_automator.py/self_healer.py/
macro_executor.py each keep their own tables in the same database
file, same sharing pattern as performance_metrics.db in Phase 20.3).
"""

import json
import sqlite3
import threading
import time
from pathlib import Path
from typing import Dict, List, Optional

from core.logger import get_logger
from skills.app_control.app_launcher import AppLauncher

logger = get_logger("ultron.app_launch_executor")

DB_PATH = Path(__file__).resolve().parent.parent / "database" / "execution.db"

_instance: Optional["AppLaunchExecutor"] = None
_instance_lock = threading.Lock()


class AppLaunchExecutor:
    """Logged execution-layer facade over skills.app_control's AppLauncher."""

    def __init__(self, db_path: Path = DB_PATH):
        self._db_path = db_path
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
        self._conn.execute("""CREATE TABLE IF NOT EXISTS app_launch_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                app_name TEXT,
                mode TEXT,
                args_json TEXT,
                as_admin INTEGER,
                success INTEGER,
                error TEXT,
                duration_ms REAL,
                timestamp REAL
            )""")
        self._conn.execute("CREATE INDEX IF NOT EXISTS idx_app_launch_name ON app_launch_events (app_name)")
        self._conn.commit()
        self._launcher = AppLauncher()

    def launch(self, app_name: str, args: Optional[List[str]] = None, as_admin: bool = False) -> Dict:
        """Launch a single app. Delegates entirely to AppLauncher.launch();
        this call just times it and logs the outcome."""
        t0 = time.time()
        try:
            result = self._launcher.launch(app_name, args=args, as_admin=as_admin)
        except Exception as exc:
            result = {"success": False, "error": str(exc)}
        duration_ms = (time.time() - t0) * 1000
        self._log("launch", app_name, args, as_admin, result, duration_ms)
        return {**result, "logged": True}

    def launch_and_wait(self, app_name: str, timeout: float = 10.0) -> Dict:
        """Launch and block until a matching window appears (or timeout)."""
        t0 = time.time()
        try:
            result = self._launcher.launch_and_wait(app_name, timeout=timeout)
        except Exception as exc:
            result = {"success": False, "error": str(exc)}
        duration_ms = (time.time() - t0) * 1000
        self._log("launch_and_wait", app_name, None, False, result, duration_ms)
        return {**result, "logged": True}

    def launch_multiple(self, app_names: List[str]) -> Dict:
        """Launch several apps back to back, logging each individually."""
        result = self._launcher.launch_multiple(app_names)
        for r in result.get("results", []):
            self._log("launch_multiple", r.get("app_name", "?"), None, False, r, None)
        return {**result, "logged": True}

    def relaunch(self, app_name: str) -> Dict:
        """Close (if running) then reopen an app fresh."""
        t0 = time.time()
        try:
            result = self._launcher.relaunch(app_name)
        except Exception as exc:
            result = {"error": str(exc)}
        duration_ms = (time.time() - t0) * 1000
        opened = result.get("opened") if isinstance(result, dict) else None
        success = bool(opened and opened.get("success")) if isinstance(opened, dict) else False
        self._log(
            "relaunch",
            app_name,
            None,
            False,
            {"success": success, "error": None if success else "relaunch did not confirm open"},
            duration_ms,
        )
        return {**result, "logged": True}

    def get_recent_launches(self, app_name: Optional[str] = None, limit: int = 20) -> List[Dict]:
        with self._lock:
            if app_name:
                rows = self._conn.execute(
                    """SELECT app_name, mode, args_json, as_admin, success, error, duration_ms, timestamp
                       FROM app_launch_events WHERE app_name = ? ORDER BY id DESC LIMIT ?""",
                    (app_name, limit),
                ).fetchall()
            else:
                rows = self._conn.execute(
                    """SELECT app_name, mode, args_json, as_admin, success, error, duration_ms, timestamp
                       FROM app_launch_events ORDER BY id DESC LIMIT ?""",
                    (limit,),
                ).fetchall()
        return [
            {
                "app_name": a,
                "mode": m,
                "args": json.loads(ar) if ar else None,
                "as_admin": bool(adm),
                "success": bool(s) if s is not None else None,
                "error": e,
                "duration_ms": d,
                "timestamp": ts,
            }
            for a, m, ar, adm, s, e, d, ts in rows
        ]

    def get_stats(self, app_name: Optional[str] = None) -> Dict:
        """Success rate for this app's launches (or all apps if omitted)."""
        with self._lock:
            if app_name:
                rows = self._conn.execute(
                    "SELECT success FROM app_launch_events WHERE app_name = ?",
                    (app_name,),
                ).fetchall()
            else:
                rows = self._conn.execute("SELECT success FROM app_launch_events").fetchall()
        n = len(rows)
        if n == 0:
            return {"app_name": app_name, "count": 0, "success_rate": None}
        successes = sum(1 for (s,) in rows if s)
        return {"app_name": app_name, "count": n, "success_rate": round(successes / n, 4)}

    def _log(
        self,
        mode: str,
        app_name: str,
        args: Optional[List[str]],
        as_admin: bool,
        result: Dict,
        duration_ms: Optional[float],
    ) -> None:
        success = result.get("success")
        error = result.get("error")
        with self._lock:
            self._conn.execute(
                """INSERT INTO app_launch_events
                   (app_name, mode, args_json, as_admin, success, error, duration_ms, timestamp)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    app_name,
                    mode,
                    json.dumps(args) if args else None,
                    1 if as_admin else 0,
                    None if success is None else (1 if success else 0),
                    error,
                    duration_ms,
                    time.time(),
                ),
            )
            self._conn.commit()
        if success is False:
            logger.info(f"app_launch_executor: '{app_name}' ({mode}) failed - {error or 'no error detail'}")


def get_app_launcher() -> AppLaunchExecutor:
    """Process-wide AppLaunchExecutor singleton."""
    global _instance
    if _instance is None:
        with _instance_lock:
            if _instance is None:
                _instance = AppLaunchExecutor()
    return _instance
