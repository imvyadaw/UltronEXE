"""
Notification Manager (Phase 20.1 - Proactive Intelligence)
==================================================
Owns the queue of things ULTRON wants to tell the user, from the
moment proactive_engine.py decides something is worth surfacing
through delivery, dismissal, or snoozing. This is the durable record
of proactive output - independent of *how* something ends up being
delivered (conversation_initiator.py decides that), this module is
just the source of truth for what's pending, what's already been
shown, and what got snoozed for later.

Lifecycle: enqueue() creates a notification in status "pending".
mark_delivered() records that it was actually shown/spoken.
dismiss() records the user closed it out. snooze() parks it until a
future time, after which get_pending() automatically surfaces it
again (a snoozed notification whose snoozed_until has passed is
treated as pending, same as an untouched one). expire_stale() sweeps
out old pending notifications nobody ever acted on, so the queue
doesn't grow forever with things that stopped being relevant.

Storage: database/proactive_intelligence.db, table notifications.
Shares the db file with user_disruption_guard.py, each owning its own
table, same pattern as turn_manager.py/response_timer.py sharing
conversation_history.db in Phase 20.
"""

import json
import sqlite3
import threading
import time
from pathlib import Path
from typing import Dict, List, Optional

DB_PATH = Path(__file__).resolve().parent.parent.parent / "database" / "proactive_intelligence.db"

_instance: Optional["NotificationManager"] = None
_instance_lock = threading.Lock()

STATUS_PENDING = "pending"
STATUS_DELIVERED = "delivered"
STATUS_DISMISSED = "dismissed"
STATUS_SNOOZED = "snoozed"
STATUS_EXPIRED = "expired"

# a pending notification nobody acted on for this long is swept out by
# expire_stale() rather than sitting in the queue forever
_DEFAULT_STALE_AFTER_SECONDS = 86400 * 3


class NotificationManager:
    """enqueue/get_pending/mark_delivered/dismiss/snooze over a
    persistent notification queue."""

    def __init__(self, db_path: Path = DB_PATH):
        self._db_path = db_path
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
        self._conn.execute("""CREATE TABLE IF NOT EXISTS notifications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_type TEXT,
                category TEXT,
                urgency_level TEXT,
                title TEXT,
                message TEXT,
                status TEXT,
                created_at REAL,
                delivered_at REAL,
                dismissed_at REAL,
                snoozed_until REAL,
                payload_json TEXT
            )""")
        self._conn.commit()

    def enqueue(self, event: Dict, urgency_level: str, message: str, payload: Optional[Dict] = None) -> Dict:
        now = time.time()
        with self._lock:
            cur = self._conn.execute(
                """INSERT INTO notifications
                   (event_type, category, urgency_level, title, message, status,
                    created_at, delivered_at, dismissed_at, snoozed_until, payload_json)
                   VALUES (?, ?, ?, ?, ?, ?, ?, NULL, NULL, NULL, ?)""",
                (
                    event.get("event_type"),
                    event.get("category"),
                    urgency_level,
                    event.get("title"),
                    message,
                    STATUS_PENDING,
                    now,
                    json.dumps(payload or {}),
                ),
            )
            self._conn.commit()
            notification_id = cur.lastrowid
        return self.get(notification_id)

    def get(self, notification_id: int) -> Optional[Dict]:
        with self._lock:
            row = self._conn.execute(
                """SELECT id, event_type, category, urgency_level, title, message, status,
                          created_at, delivered_at, dismissed_at, snoozed_until, payload_json
                   FROM notifications WHERE id = ?""",
                (notification_id,),
            ).fetchone()
        return self._row_to_notification(row) if row else None

    def get_pending(self, limit: int = 20) -> List[Dict]:
        """Pending notifications, plus any snoozed ones whose
        snoozed_until has passed (auto-restored to pending), ordered
        most-urgent-first then oldest-first."""
        self._restore_expired_snoozes()
        with self._lock:
            rows = self._conn.execute(
                """SELECT id, event_type, category, urgency_level, title, message, status,
                          created_at, delivered_at, dismissed_at, snoozed_until, payload_json
                   FROM notifications WHERE status = ?
                   ORDER BY CASE urgency_level
                       WHEN 'critical' THEN 0 WHEN 'high' THEN 1
                       WHEN 'medium' THEN 2 ELSE 3 END, created_at ASC
                   LIMIT ?""",
                (STATUS_PENDING, limit),
            ).fetchall()
        return [self._row_to_notification(r) for r in rows]

    def mark_delivered(self, notification_id: int) -> Optional[Dict]:
        now = time.time()
        with self._lock:
            self._conn.execute(
                "UPDATE notifications SET status = ?, delivered_at = ? WHERE id = ?",
                (STATUS_DELIVERED, now, notification_id),
            )
            self._conn.commit()
        return self.get(notification_id)

    def dismiss(self, notification_id: int) -> Optional[Dict]:
        now = time.time()
        with self._lock:
            self._conn.execute(
                "UPDATE notifications SET status = ?, dismissed_at = ? WHERE id = ?",
                (STATUS_DISMISSED, now, notification_id),
            )
            self._conn.commit()
        return self.get(notification_id)

    def snooze(self, notification_id: int, minutes: float) -> Optional[Dict]:
        snoozed_until = time.time() + minutes * 60.0
        with self._lock:
            self._conn.execute(
                "UPDATE notifications SET status = ?, snoozed_until = ? WHERE id = ?",
                (STATUS_SNOOZED, snoozed_until, notification_id),
            )
            self._conn.commit()
        return self.get(notification_id)

    def expire_stale(self, older_than_seconds: float = _DEFAULT_STALE_AFTER_SECONDS) -> int:
        """Sweeps pending notifications older than the cutoff to
        status expired. Returns how many were swept."""
        cutoff = time.time() - older_than_seconds
        with self._lock:
            cur = self._conn.execute(
                "UPDATE notifications SET status = ? WHERE status = ? AND created_at < ?",
                (STATUS_EXPIRED, STATUS_PENDING, cutoff),
            )
            self._conn.commit()
            return cur.rowcount

    def get_recent(self, limit: int = 20) -> List[Dict]:
        with self._lock:
            rows = self._conn.execute(
                """SELECT id, event_type, category, urgency_level, title, message, status,
                          created_at, delivered_at, dismissed_at, snoozed_until, payload_json
                   FROM notifications ORDER BY id DESC LIMIT ?""",
                (limit,),
            ).fetchall()
        return [self._row_to_notification(r) for r in rows]

    def _restore_expired_snoozes(self) -> None:
        now = time.time()
        with self._lock:
            self._conn.execute(
                "UPDATE notifications SET status = ?, snoozed_until = NULL "
                "WHERE status = ? AND snoozed_until IS NOT NULL AND snoozed_until <= ?",
                (STATUS_PENDING, STATUS_SNOOZED, now),
            )
            self._conn.commit()

    @staticmethod
    def _row_to_notification(row) -> Dict:
        (
            id_,
            event_type,
            category,
            urgency_level,
            title,
            message,
            status,
            created_at,
            delivered_at,
            dismissed_at,
            snoozed_until,
            payload_json,
        ) = row
        try:
            payload = json.loads(payload_json) if payload_json else {}
        except Exception:
            payload = {}
        return {
            "id": id_,
            "event_type": event_type,
            "category": category,
            "urgency_level": urgency_level,
            "title": title,
            "message": message,
            "status": status,
            "created_at": created_at,
            "delivered_at": delivered_at,
            "dismissed_at": dismissed_at,
            "snoozed_until": snoozed_until,
            "payload": payload,
        }


def get_notification_manager() -> NotificationManager:
    """Process-wide NotificationManager singleton."""
    global _instance
    if _instance is None:
        with _instance_lock:
            if _instance is None:
                _instance = NotificationManager()
    return _instance
