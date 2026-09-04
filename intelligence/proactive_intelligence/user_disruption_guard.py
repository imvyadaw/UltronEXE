"""
User Disruption Guard (Phase 20.1 - Proactive Intelligence)
==================================================
Decides whether right now is actually an acceptable moment to
surface something to the user, given how urgent it is. This is the
module standing between "ULTRON noticed something" and "ULTRON says
something" - without it, every detected event would go straight at
the user regardless of quiet hours, an active manual do-not-disturb,
being on a call, or having a fullscreen app up, which is exactly the
kind of nagging-assistant behavior this package exists to avoid.

evaluate() combines, in order: an active manual DND window, configured
quiet hours, situational context the caller passes in (in_call,
fullscreen_active, idle_seconds), and a per-category cooldown so the
same kind of thing isn't re-surfaced every time it's re-detected.
Critical-urgency events can bypass DND/quiet-hours/context if
allow_critical_during_dnd is enabled (the default) - a security alert
still shouldn't wait for quiet hours to end - but never bypass the
cooldown, since a genuine repeat within the cooldown window is a
notification_manager.py delivery concern, not a reason to interrupt
twice.

Storage: database/proactive_intelligence.db, table guard_settings (a
single row holding quiet hours / DND state) and table
interruption_log (every evaluate() call, used for the cooldown lookup
and for audit/history).
"""

import sqlite3
import threading
import time
from pathlib import Path
from typing import Dict, Optional

DB_PATH = Path(__file__).resolve().parent.parent.parent / "database" / "proactive_intelligence.db"

_instance: Optional["UserDisruptionGuard"] = None
_instance_lock = threading.Lock()

DECISION_ALLOW = "allow"
DECISION_DEFER = "defer"
DECISION_SUPPRESS = "suppress"

URGENCY_CRITICAL = "critical"

# default quiet hours, expressed as minutes-since-midnight so an
# overnight window (23:00 -> 07:00) is just as easy to check as a
# same-day one
_DEFAULT_QUIET_START_MINUTE = 23 * 60
_DEFAULT_QUIET_END_MINUTE = 7 * 60

# how long a suppressed/deferred category is held back from
# re-triggering a fresh interruption decision - a low-urgency system
# notice shouldn't re-ask every few minutes, a security alert should
_CATEGORY_COOLDOWN_SECONDS = {
    "security": 60,
    "deadline": 300,
    "system": 900,
    "reminder": 300,
    "communication": 300,
    "task_complete": 300,
    "routine": 3600,
}
_DEFAULT_COOLDOWN_SECONDS = 300

# beyond this much idle time, assume the user has stepped away and
# isn't there to be interrupted at all
_IDLE_AWAY_SECONDS = 600


class UserDisruptionGuard:
    """evaluate(event, urgency_level, context) -> {"decision", "reason",
    "defer_until", "reasons"}; also owns DND/quiet-hours settings."""

    def __init__(self, db_path: Path = DB_PATH):
        self._db_path = db_path
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
        self._conn.execute("""CREATE TABLE IF NOT EXISTS guard_settings (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                quiet_start_minute INTEGER,
                quiet_end_minute INTEGER,
                quiet_hours_enabled INTEGER,
                dnd_enabled INTEGER,
                dnd_until REAL,
                allow_critical_during_dnd INTEGER,
                updated_at REAL
            )""")
        self._conn.execute("""CREATE TABLE IF NOT EXISTS interruption_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_type TEXT,
                category TEXT,
                urgency_level TEXT,
                decision TEXT,
                reason TEXT,
                timestamp REAL
            )""")
        self._conn.commit()
        self._ensure_default_settings()

    def evaluate(self, event: Dict, urgency_level: str, context: Optional[Dict] = None) -> Dict:
        context = context or {}
        now = time.time()
        reasons = []
        category = event.get("category")
        event_type = event.get("event_type")
        is_critical = urgency_level == URGENCY_CRITICAL

        # cooldown always applies, even to critical events - a real
        # repeat within the window is a delivery/dedup concern, not a
        # reason to force a second interruption decision
        cooldown_until = self._cooldown_active_until(category, now)
        if cooldown_until is not None:
            reasons.append(f"category '{category}' interrupted the user within its cooldown window")
            return self._log_and_return(
                event_type,
                category,
                urgency_level,
                DECISION_SUPPRESS,
                "cooldown active for this category",
                reasons,
                defer_until=None,
            )

        settings = self._get_settings()

        dnd_active = bool(settings["dnd_enabled"]) and (settings["dnd_until"] is None or now < settings["dnd_until"])
        if dnd_active:
            if is_critical and settings["allow_critical_during_dnd"]:
                reasons.append("manual DND is active but urgency is critical and critical bypass is allowed")
            else:
                reasons.append("manual do-not-disturb is currently active")
                defer_until = settings["dnd_until"]
                return self._log_and_return(
                    event_type,
                    category,
                    urgency_level,
                    DECISION_DEFER,
                    "do-not-disturb active",
                    reasons,
                    defer_until=defer_until,
                )

        if settings["quiet_hours_enabled"] and self._in_quiet_hours(now, settings):
            if is_critical and settings["allow_critical_during_dnd"]:
                reasons.append("inside quiet hours but urgency is critical and critical bypass is allowed")
            else:
                defer_until = self._next_quiet_hours_end(now, settings)
                reasons.append("currently inside configured quiet hours")
                return self._log_and_return(
                    event_type,
                    category,
                    urgency_level,
                    DECISION_DEFER,
                    "quiet hours active",
                    reasons,
                    defer_until=defer_until,
                )

        if context.get("in_call") and not is_critical:
            reasons.append("user appears to be on a call")
            return self._log_and_return(
                event_type, category, urgency_level, DECISION_DEFER, "user is on a call", reasons, defer_until=None
            )

        if context.get("fullscreen_active") and not is_critical:
            reasons.append("user is in a fullscreen app (likely a video/game/presentation)")
            return self._log_and_return(
                event_type, category, urgency_level, DECISION_DEFER, "fullscreen app active", reasons, defer_until=None
            )

        idle_seconds = context.get("idle_seconds", 0) or 0
        if idle_seconds >= _IDLE_AWAY_SECONDS:
            reasons.append(f"user idle for {idle_seconds:.0f}s - likely away from the machine")
            return self._log_and_return(
                event_type, category, urgency_level, DECISION_DEFER, "user appears away", reasons, defer_until=None
            )

        reasons.append("no DND/quiet-hours/context/cooldown reason to hold this back")
        return self._log_and_return(
            event_type, category, urgency_level, DECISION_ALLOW, "clear to surface now", reasons, defer_until=None
        )

    def set_dnd(self, enabled: bool, minutes: Optional[float] = None, allow_critical: Optional[bool] = None) -> Dict:
        """Turn manual do-not-disturb on/off. minutes, if given, sets a
        timed DND window; omitting it (while enabling) means "until
        turned off manually"."""
        dnd_until = (time.time() + minutes * 60.0) if (enabled and minutes) else None
        with self._lock:
            current = self._get_settings_locked()
            self._conn.execute(
                """UPDATE guard_settings SET dnd_enabled = ?, dnd_until = ?,
                   allow_critical_during_dnd = ?, updated_at = ? WHERE id = 1""",
                (
                    int(enabled),
                    dnd_until,
                    int(allow_critical) if allow_critical is not None else current["allow_critical_during_dnd"],
                    time.time(),
                ),
            )
            self._conn.commit()
        return self._get_settings()

    def set_quiet_hours(
        self, start_hour: int, start_minute: int, end_hour: int, end_minute: int, enabled: bool = True
    ) -> Dict:
        start = start_hour * 60 + start_minute
        end = end_hour * 60 + end_minute
        with self._lock:
            self._conn.execute(
                """UPDATE guard_settings SET quiet_start_minute = ?, quiet_end_minute = ?,
                   quiet_hours_enabled = ?, updated_at = ? WHERE id = 1""",
                (start, end, int(enabled), time.time()),
            )
            self._conn.commit()
        return self._get_settings()

    def get_settings(self) -> Dict:
        return self._get_settings()

    def get_recent_decisions(self, limit: int = 20) -> list:
        with self._lock:
            rows = self._conn.execute(
                """SELECT id, event_type, category, urgency_level, decision, reason, timestamp
                   FROM interruption_log ORDER BY id DESC LIMIT ?""",
                (limit,),
            ).fetchall()
        return [
            {
                "id": r[0],
                "event_type": r[1],
                "category": r[2],
                "urgency_level": r[3],
                "decision": r[4],
                "reason": r[5],
                "timestamp": r[6],
            }
            for r in rows
        ]

    def _cooldown_active_until(self, category: str, now: float) -> Optional[float]:
        cooldown = _CATEGORY_COOLDOWN_SECONDS.get(category, _DEFAULT_COOLDOWN_SECONDS)
        with self._lock:
            row = self._conn.execute(
                """SELECT timestamp FROM interruption_log
                   WHERE category = ? AND decision != ? ORDER BY id DESC LIMIT 1""",
                (category, DECISION_SUPPRESS),
            ).fetchone()
        if row is None:
            return None
        last_ts = row[0]
        if (now - last_ts) < cooldown:
            return last_ts + cooldown
        return None

    def _in_quiet_hours(self, now: float, settings: Dict) -> bool:
        minute_of_day = self._minute_of_day(now)
        start, end = settings["quiet_start_minute"], settings["quiet_end_minute"]
        if start == end:
            return False
        if start < end:
            return start <= minute_of_day < end
        # overnight window, e.g. 23:00 -> 07:00
        return minute_of_day >= start or minute_of_day < end

    def _next_quiet_hours_end(self, now: float, settings: Dict) -> float:
        end_minute = settings["quiet_end_minute"]
        minute_of_day = self._minute_of_day(now)
        day_start = now - (minute_of_day * 60) - (now % 60)
        minutes_until_end = (end_minute - minute_of_day) % (24 * 60)
        return day_start + minutes_until_end * 60

    @staticmethod
    def _minute_of_day(ts: float) -> int:
        local = time.localtime(ts)
        return local.tm_hour * 60 + local.tm_min

    def _ensure_default_settings(self) -> None:
        with self._lock:
            row = self._conn.execute("SELECT id FROM guard_settings WHERE id = 1").fetchone()
            if row is None:
                self._conn.execute(
                    """INSERT INTO guard_settings
                       (id, quiet_start_minute, quiet_end_minute, quiet_hours_enabled,
                        dnd_enabled, dnd_until, allow_critical_during_dnd, updated_at)
                       VALUES (1, ?, ?, 1, 0, NULL, 1, ?)""",
                    (_DEFAULT_QUIET_START_MINUTE, _DEFAULT_QUIET_END_MINUTE, time.time()),
                )
                self._conn.commit()

    def _get_settings(self) -> Dict:
        with self._lock:
            return self._get_settings_locked()

    def _get_settings_locked(self) -> Dict:
        row = self._conn.execute("""SELECT quiet_start_minute, quiet_end_minute, quiet_hours_enabled,
                      dnd_enabled, dnd_until, allow_critical_during_dnd
               FROM guard_settings WHERE id = 1""").fetchone()
        quiet_start, quiet_end, quiet_enabled, dnd_enabled, dnd_until, allow_critical = row
        return {
            "quiet_start_minute": quiet_start,
            "quiet_end_minute": quiet_end,
            "quiet_hours_enabled": bool(quiet_enabled),
            "dnd_enabled": bool(dnd_enabled),
            "dnd_until": dnd_until,
            "allow_critical_during_dnd": bool(allow_critical),
        }

    def _log_and_return(
        self,
        event_type: str,
        category: str,
        urgency_level: str,
        decision: str,
        reason: str,
        reasons: list,
        defer_until: Optional[float],
    ) -> Dict:
        now = time.time()
        with self._lock:
            self._conn.execute(
                """INSERT INTO interruption_log
                   (event_type, category, urgency_level, decision, reason, timestamp)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (event_type, category, urgency_level, decision, reason, now),
            )
            self._conn.commit()
        return {"decision": decision, "reason": reason, "defer_until": defer_until, "reasons": reasons}


def get_user_disruption_guard() -> UserDisruptionGuard:
    """Process-wide UserDisruptionGuard singleton."""
    global _instance
    if _instance is None:
        with _instance_lock:
            if _instance is None:
                _instance = UserDisruptionGuard()
    return _instance
