"""
Auto Player (Phase 24 - Execution)
==================================================
One playback call regardless of which of Ultron's two existing
step-recording systems produced the recording:

    automation/RPA/player.py's RPAPlayer   - richer step types
                                              (click/key/type_text/wait/
                                              open_app/run_tool/screenshot),
                                              recorded by RPARecorder.
    automation/macro/macro.py's MacroRecorder.play_macro() - simpler
                                              click+key replay.

Same relationship to those two as auto_optimizer.py has to
path_optimizer.py/cache_strategist.py in Phase 20.3: this module owns
no replay logic of its own, it just calls play()/dry_run() +
play_macro() on the existing players and logs the outcome so
self_healer.py/macro_executor.py have something to act on.

Storage: database/execution.db, table playback_events (this module's
own table, shared with app_launcher.py's/web_automator.py's/
self_healer.py's/macro_executor.py's own tables in the same file).
"""

import sqlite3
import threading
import time
from pathlib import Path
from typing import Dict, List, Optional

from core.logger import get_logger
from automation.RPA.player import RPAPlayer
from automation.macro.macro import MacroRecorder

logger = get_logger("ultron.auto_player")

DB_PATH = Path(__file__).resolve().parent.parent / "database" / "execution.db"

_instance: Optional["AutoPlayer"] = None
_instance_lock = threading.Lock()


class AutoPlayer:
    """Unified replay of RPA scripts (automation/RPA) and macros
    (automation/macro), with every playback logged."""

    def __init__(self, db_path: Path = DB_PATH):
        self._db_path = db_path
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
        self._conn.execute("""CREATE TABLE IF NOT EXISTS playback_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                kind TEXT,
                name TEXT,
                speed REAL,
                loop INTEGER,
                success INTEGER,
                error TEXT,
                duration_ms REAL,
                timestamp REAL
            )""")
        self._conn.execute("CREATE INDEX IF NOT EXISTS idx_playback_kind_name ON playback_events (kind, name)")
        self._conn.commit()
        self._rpa = RPAPlayer()
        self._macro = MacroRecorder()

    def play_script(self, script_name: str, speed: float = 1.0, loop: int = 1) -> Dict:
        """Replay a desktop RPA script recorded by automation/RPA/recorder.py."""
        t0 = time.time()
        try:
            result = self._rpa.play(script_name, speed=speed, loop=loop)
        except Exception as exc:
            result = {"success": False, "error": str(exc)}
        self._log("script", script_name, speed, loop, result, (time.time() - t0) * 1000)
        return {**result, "logged": True}

    def dry_run_script(self, script_name: str) -> Dict:
        """List a script's steps without executing them - passthrough to
        RPAPlayer.dry_run(), not logged as a real playback attempt."""
        try:
            return self._rpa.dry_run(script_name)
        except Exception as exc:
            return {"error": str(exc)}

    def play_macro(self, macro_name: str, speed: float = 1.0) -> Dict:
        """Replay a macro recorded by automation/macro/macro.py's MacroRecorder."""
        t0 = time.time()
        try:
            result = self._macro.play_macro(macro_name, speed=speed)
        except Exception as exc:
            result = {"success": False, "error": str(exc)}
        self._log("macro", macro_name, speed, 1, result, (time.time() - t0) * 1000)
        return {**result, "logged": True}

    def list_available(self) -> Dict:
        """Merged view of playable RPA scripts and macros."""
        try:
            scripts = self._rpa.list_scripts()
        except Exception as exc:
            scripts = {"error": str(exc)}
        try:
            macros = self._macro.list_macros()
        except Exception as exc:
            macros = {"error": str(exc)}
        return {"scripts": scripts, "macros": macros}

    def get_recent_playbacks(
        self, kind: Optional[str] = None, name: Optional[str] = None, limit: int = 20
    ) -> List[Dict]:
        clauses, params = [], []
        if kind is not None:
            clauses.append("kind = ?")
            params.append(kind)
        if name is not None:
            clauses.append("name = ?")
            params.append(name)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        params.append(limit)
        with self._lock:
            rows = self._conn.execute(
                f"""SELECT kind, name, speed, loop, success, error, duration_ms, timestamp
                    FROM playback_events {where} ORDER BY id DESC LIMIT ?""",
                params,
            ).fetchall()
        return [
            {
                "kind": k,
                "name": n,
                "speed": sp,
                "loop": lp,
                "success": bool(s) if s is not None else None,
                "error": e,
                "duration_ms": d,
                "timestamp": ts,
            }
            for k, n, sp, lp, s, e, d, ts in rows
        ]

    def _log(self, kind: str, name: str, speed: float, loop: int, result: Dict, duration_ms: float) -> None:
        success = result.get("success")
        error = result.get("error")
        with self._lock:
            self._conn.execute(
                """INSERT INTO playback_events
                   (kind, name, speed, loop, success, error, duration_ms, timestamp)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    kind,
                    name,
                    speed,
                    loop,
                    None if success is None else (1 if success else 0),
                    error,
                    duration_ms,
                    time.time(),
                ),
            )
            self._conn.commit()
        if success is False:
            logger.info(f"auto_player: {kind} '{name}' failed - {error or 'no error detail'}")


def get_auto_player() -> AutoPlayer:
    """Process-wide AutoPlayer singleton."""
    global _instance
    if _instance is None:
        with _instance_lock:
            if _instance is None:
                _instance = AutoPlayer()
    return _instance
