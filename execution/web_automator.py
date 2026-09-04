"""
Web Automator (Phase 24 - Execution)
==================================================
One entry point over Ultron's two existing, differently-shaped web
automation paths:

    browser/automation/automation.py's BrowserAutomation - drives the
        user's *already-open* Chrome/Edge/Firefox window via UI
        automation (scroll, navigate). No extra dependency - reuses
        whichever browser the user already has up.
    automation/RPA/web_rpa.py's WebRPA - drives a *separate* Selenium
        browser through named, saved scripts (navigate/fill/click/
        extract steps) or one-off ad hoc step lists. Needs Selenium +
        webdriver-manager (skills/web/form_filler.py's HAS_SELENIUM
        guard); if that's not installed, script-based methods below
        return a clear error instead of raising, same graceful-
        degradation posture as every optional-dependency guard
        elsewhere in Ultron.

live_* methods below never touch Selenium; script_* methods never
touch the user's real browser window - the two paths don't overlap,
so both can be used side by side safely.

Storage: database/execution.db, table web_automation_events (this
module's own table, shared with app_launcher.py's/auto_player.py's/
self_healer.py's/macro_executor.py's own tables in the same file).
"""

import sqlite3
import threading
import time
from pathlib import Path
from typing import Dict, List, Optional

from core.logger import get_logger
from browser.automation.automation import BrowserAutomation

try:
    from automation.RPA.web_rpa import WebRPA
    from skills.web.form_filler import HAS_SELENIUM
except ImportError:
    WebRPA = None
    HAS_SELENIUM = False

logger = get_logger("ultron.web_automator")

DB_PATH = Path(__file__).resolve().parent.parent / "database" / "execution.db"

_instance: Optional["WebAutomator"] = None
_instance_lock = threading.Lock()


class WebAutomator:
    """Logged execution-layer facade over BrowserAutomation (live window)
    and WebRPA (scripted Selenium session, lazily created)."""

    def __init__(self, db_path: Path = DB_PATH):
        self._db_path = db_path
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
        self._conn.execute("""CREATE TABLE IF NOT EXISTS web_automation_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                mode TEXT,
                target TEXT,
                success INTEGER,
                error TEXT,
                duration_ms REAL,
                timestamp REAL
            )""")
        self._conn.commit()
        self._live = BrowserAutomation()
        self._web_rpa = None  # lazy - only created once a script_* method is actually called

    def _get_web_rpa(self, headless: bool = True):
        if WebRPA is None or not HAS_SELENIUM:
            return None
        if self._web_rpa is None:
            self._web_rpa = WebRPA(headless=headless)
        return self._web_rpa

    # -- live browser window (no extra dependency) -------------------------
    def live_scroll(self, direction: str = "down", amount: int = 300, browser: Optional[str] = None) -> Dict:
        t0 = time.time()
        try:
            result = self._live.browser_scroll(direction, amount, browser=browser)
        except Exception as exc:
            result = {"success": False, "error": str(exc)}
        self._log("live_scroll", browser or "auto-detect", result, (time.time() - t0) * 1000)
        return {**result, "logged": True}

    def live_navigate(self, action: str, browser: Optional[str] = None) -> Dict:
        t0 = time.time()
        try:
            result = self._live.browser_navigate(action, browser=browser)
        except Exception as exc:
            result = {"success": False, "error": str(exc)}
        self._log("live_navigate", browser or "auto-detect", result, (time.time() - t0) * 1000)
        return {**result, "logged": True}

    # -- scripted Selenium session (needs selenium + webdriver-manager) ----
    def script_play(self, script_name: str, stop_on_error: bool = True, headless: bool = True) -> Dict:
        rpa = self._get_web_rpa(headless=headless)
        if rpa is None:
            return {
                "success": False,
                "error": "selenium/webdriver-manager not installed - " "run: pip install selenium webdriver-manager",
            }
        t0 = time.time()
        try:
            result = rpa.play(script_name, stop_on_error=stop_on_error)
        except Exception as exc:
            result = {"success": False, "error": str(exc)}
        self._log("script_play", script_name, result, (time.time() - t0) * 1000)
        return {**result, "logged": True}

    def script_run_steps(self, steps: List[Dict], stop_on_error: bool = True, headless: bool = True) -> Dict:
        rpa = self._get_web_rpa(headless=headless)
        if rpa is None:
            return {
                "success": False,
                "error": "selenium/webdriver-manager not installed - " "run: pip install selenium webdriver-manager",
            }
        t0 = time.time()
        try:
            result = rpa.run_ad_hoc(steps, stop_on_error=stop_on_error)
        except Exception as exc:
            result = {"success": False, "error": str(exc)}
        self._log("script_run_steps", f"{len(steps)} ad hoc steps", result, (time.time() - t0) * 1000)
        return {**result, "logged": True}

    def close_session(self) -> Dict:
        """Close the lazily-created Selenium session, if one was ever opened."""
        if self._web_rpa is None:
            return {"success": True, "note": "no scripted session was open"}
        try:
            result = self._web_rpa.close()
        except Exception as exc:
            result = {"success": False, "error": str(exc)}
        self._web_rpa = None
        return result

    def get_recent_events(self, mode: Optional[str] = None, limit: int = 20) -> List[Dict]:
        with self._lock:
            if mode:
                rows = self._conn.execute(
                    """SELECT mode, target, success, error, duration_ms, timestamp
                       FROM web_automation_events WHERE mode = ? ORDER BY id DESC LIMIT ?""",
                    (mode, limit),
                ).fetchall()
            else:
                rows = self._conn.execute(
                    """SELECT mode, target, success, error, duration_ms, timestamp
                       FROM web_automation_events ORDER BY id DESC LIMIT ?""",
                    (limit,),
                ).fetchall()
        return [
            {
                "mode": m,
                "target": t,
                "success": bool(s) if s is not None else None,
                "error": e,
                "duration_ms": d,
                "timestamp": ts,
            }
            for m, t, s, e, d, ts in rows
        ]

    def _log(self, mode: str, target: str, result: Dict, duration_ms: float) -> None:
        success = result.get("success")
        error = result.get("error")
        with self._lock:
            self._conn.execute(
                """INSERT INTO web_automation_events (mode, target, success, error, duration_ms, timestamp)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (mode, target, None if success is None else (1 if success else 0), error, duration_ms, time.time()),
            )
            self._conn.commit()
        if success is False:
            logger.info(f"web_automator: {mode} '{target}' failed - {error or 'no error detail'}")


def get_web_automator() -> WebAutomator:
    """Process-wide WebAutomator singleton."""
    global _instance
    if _instance is None:
        with _instance_lock:
            if _instance is None:
                _instance = WebAutomator()
    return _instance
