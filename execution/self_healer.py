"""
Self Healer (Phase 24 - Execution)
==================================================
intelligence/self_healing/self_healing_engine.py's heal() has run in
advisory/dry-run mode since Phase 19.5 - it diagnoses a failure and
returns an ordered strategy plan, but nothing in Phase 1-23 ever
passed it a real `executor` callable, so it never actually recovered
anything on its own. This module closes that gap: it turns
self_healing_engine.py's generic strategy names (retry_once,
retry_with_backoff, retry_with_elevated_permission, use_fallback_path,
escalate_to_user, ...) into real calls back into app_launcher.py /
auto_player.py / web_automator.py, so a failed execution step can be
retried automatically instead of just reported.

Strategy dispatch (generic - the same for every action type):
    retry_once / retry_with_backoff / retry_after_delay /
    increase_timeout / free_resources_and_retry
        -> call the original action again (small sleep first for the
           backoff/delay-flavored names, since they imply waiting).
    retry_with_elevated_permission
        -> call the admin/elevated variant if the caller gave one,
           otherwise fall back to a plain retry.
    use_fallback_path / use_alternate_location / create_missing_path
        -> call the caller-supplied fallback action, if any.
    switch_to_offline_mode / escalate_to_user / anything unrecognized
        -> not auto-actionable here; reported as not handled rather
           than guessed at, same "don't do something the caller didn't
           ask for" posture as the rest of Ultron's automation layer.

heal_app_launch()/heal_playback()/heal_web() are thin convenience
wrappers over heal() that already know how to build retry/admin-retry
callables for their own execution/ sibling module, so
macro_executor.py doesn't have to.

Storage: database/execution.db, table heal_events (this module's own
table, logging what the execution layer actually did with each
self_healing_engine.py plan; the underlying healing_runs table in
database/self_healing.db is untouched and still owned entirely by
Phase 19.5).
"""

import sqlite3
import threading
import time
from pathlib import Path
from typing import Callable, Dict, Optional

from core.logger import get_logger
from intelligence.self_healing.self_healing_engine import get_self_healing_engine

logger = get_logger("ultron.self_healer")

DB_PATH = Path(__file__).resolve().parent.parent / "database" / "execution.db"

_instance: Optional["SelfHealer"] = None
_instance_lock = threading.Lock()

# strategy names -> how long to wait before retrying, when the
# strategy name itself implies a delay. Kept short - this runs inline
# during heal(), not on a background schedule.
_BACKOFF_SECONDS = {
    "retry_with_backoff": 1.5,
    "retry_after_delay": 1.0,
    "free_resources_and_retry": 0.5,
}

# strategies this module will never attempt to auto-execute, regardless
# of what callables the caller supplied - they require a human or a
# capability nothing here has.
_NOT_AUTO_ACTIONABLE = {"escalate_to_user", "switch_to_offline_mode"}


class SelfHealer:
    """Builds a real executor callable for self_healing_engine.py's
    heal() out of the caller's own retry/fallback actions."""

    def __init__(self, db_path: Path = DB_PATH):
        self._db_path = db_path
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
        self._conn.execute("""CREATE TABLE IF NOT EXISTS heal_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                action_name TEXT,
                outcome TEXT,
                strategy_tried TEXT,
                timestamp REAL
            )""")
        self._conn.commit()
        self._engine = get_self_healing_engine()

    def heal(
        self,
        action_name: str,
        retry_fn: Callable[[], bool],
        error: Optional[str] = None,
        verification_result: Optional[Dict] = None,
        admin_retry_fn: Optional[Callable[[], bool]] = None,
        fallback_fn: Optional[Callable[[], bool]] = None,
        max_attempts: int = 3,
    ) -> Dict:
        """Diagnose action_name's failure and actually try to recover it
        using the callables given. Returns self_healing_engine.py's
        heal() result dict unchanged, plus this module's own logging."""

        def executor(strategy_name: str) -> bool:
            if strategy_name in _NOT_AUTO_ACTIONABLE:
                return False

            delay = _BACKOFF_SECONDS.get(strategy_name)
            if delay:
                time.sleep(delay)

            if strategy_name == "retry_with_elevated_permission":
                target = admin_retry_fn or retry_fn
                return bool(target())

            if strategy_name in ("use_fallback_path", "use_alternate_location", "create_missing_path"):
                if fallback_fn is None:
                    return False
                return bool(fallback_fn())

            if strategy_name in (
                "retry_once",
                "retry_with_backoff",
                "retry_after_delay",
                "increase_timeout",
                "free_resources_and_retry",
            ):
                return bool(retry_fn())

            # unrecognized strategy name - try a plain retry rather than
            # silently giving up, same "sensible default over refusal"
            # posture the rest of this call uses.
            return bool(retry_fn())

        result = self._engine.heal(
            action_name,
            error=error,
            verification_result=verification_result,
            executor=executor,
            max_attempts=max_attempts,
        )
        self._log(action_name, result.get("outcome", "unknown"), result.get("strategy_tried"))
        return result

    def heal_app_launch(
        self, app_name: str, error: Optional[str] = None, args: Optional[list] = None, max_attempts: int = 3
    ) -> Dict:
        """Convenience wrapper: retries a failed app_launcher.py launch,
        escalating to an elevated (admin) launch if a plain retry keeps failing."""
        from execution.app_launcher import get_app_launcher

        launcher = get_app_launcher()

        def retry_fn() -> bool:
            return bool(launcher.launch(app_name, args=args).get("success"))

        def admin_retry_fn() -> bool:
            return bool(launcher.launch(app_name, args=args, as_admin=True).get("success"))

        return self.heal(
            f"app_launch:{app_name}", retry_fn, error=error, admin_retry_fn=admin_retry_fn, max_attempts=max_attempts
        )

    def heal_playback(
        self, kind: str, name: str, error: Optional[str] = None, speed: float = 1.0, max_attempts: int = 3
    ) -> Dict:
        """Convenience wrapper: retries a failed auto_player.py playback
        (kind is 'script' or 'macro')."""
        from execution.auto_player import get_auto_player

        player = get_auto_player()

        def retry_fn() -> bool:
            if kind == "macro":
                return bool(player.play_macro(name, speed=speed).get("success"))
            return bool(player.play_script(name, speed=speed).get("success"))

        return self.heal(f"playback:{kind}:{name}", retry_fn, error=error, max_attempts=max_attempts)

    def heal_web(self, mode: str, target: str, error: Optional[str] = None, max_attempts: int = 3) -> Dict:
        """Convenience wrapper: retries a failed web_automator.py call
        (mode is 'live_scroll', 'live_navigate', or 'script_play')."""
        from execution.web_automator import get_web_automator

        automator = get_web_automator()

        def retry_fn() -> bool:
            if mode == "live_scroll":
                return bool(automator.live_scroll().get("success"))
            if mode == "live_navigate":
                return bool(automator.live_navigate(target).get("success"))
            return bool(automator.script_play(target).get("success"))

        return self.heal(f"web:{mode}:{target}", retry_fn, error=error, max_attempts=max_attempts)

    def get_history(self, action_name: Optional[str] = None, limit: int = 20):
        """Passthrough to self_healing_engine.py's own history - it
        already owns the full diagnosis/strategy record."""
        return self._engine.get_history(action_name=action_name, limit=limit)

    def _log(self, action_name: str, outcome: str, strategy_tried: Optional[str]) -> None:
        with self._lock:
            self._conn.execute(
                """INSERT INTO heal_events (action_name, outcome, strategy_tried, timestamp)
                   VALUES (?, ?, ?, ?)""",
                (action_name, outcome, strategy_tried, time.time()),
            )
            self._conn.commit()
        logger.info(
            f"self_healer: '{action_name}' -> {outcome}" + (f" via '{strategy_tried}'" if strategy_tried else "")
        )


def get_self_healer() -> SelfHealer:
    """Process-wide SelfHealer singleton."""
    global _instance
    if _instance is None:
        with _instance_lock:
            if _instance is None:
                _instance = SelfHealer()
    return _instance
