"""Smart notification routing
==============================
A small priority/quiet-hours rule engine that sits in front of
windows/notifications/toasts.py's ToastNotifier and decides WHETHER
and WHEN a given notification should actually be shown, rather than
sending one directly. Three related-but-distinct pieces already exist
and this module is glue, not a replacement for any of them:
  - windows/notifications/toasts.py's ToastNotifier just shows a toast
    right now, unconditionally - no concept of priority or timing.
  - system_control/ui/notification_manager.py controls Windows'
    OS-level notification SETTINGS (master toggle, per-app enable,
    Focus Assist mode) - this module reads that state (via
    get_focus_assist_mode()) to decide whether to hold a
    notification back, but never changes those settings itself.
  - intelligence/proactive_intelligence/notification_manager.py owns
    the durable queue of ULTRON's own *proactive* output end-to-end
    (enqueue/deliver/dismiss/snooze) - that module governs whether
    ULTRON decides something is worth telling the user at all. This
    module is downstream of that decision: given a notification any
    caller wants shown, decide the right moment (respecting quiet
    hours and Focus Assist) and hand it to ToastNotifier when the
    moment is right.

A "rule" is a named quiet-hours/priority policy: {quiet_hours_start,
quiet_hours_end, min_priority_during_quiet_hours,
suppress_during_focus_assist}, persisted to
storage/cache/notification_rules/<rule_name>.json. route() evaluates
the named rule (or a bare default) against the current time and Focus
Assist state; if the notification should wait, it's appended to an
in-memory/on-disk queue instead of shown, and a later flush_queued()
call (e.g. once quiet hours end) delivers everything that's still
relevant.

Nothing here changes system state or sends anything the user can't
easily dismiss - showing/queuing/dropping a toast is fully reversible
and low-stakes, so no method in this module is confirm-gated (same
class of judgment call as notification_manager.py's own preference
toggles, minus the one undocumented-blob exception that module has).
"""

import json
import time as _time
from pathlib import Path
from typing import Dict, List, Optional

from system_control.ui.notification_manager import NotificationManager
from windows.notifications.toasts import ToastNotifier

RULES_DIR = Path(__file__).resolve().parents[2] / "storage" / "cache" / "notification_rules"
QUEUE_PATH = Path(__file__).resolve().parents[2] / "storage" / "cache" / "notification_queue.json"
_PRIORITY_ORDER = {"low": 0, "normal": 1, "high": 2, "urgent": 3}


class SmartNotificationRouter:
    """Decide whether a notification should be shown now, queued for
    later, or dropped - based on a named quiet-hours/priority rule and
    the current Focus Assist state - then hand it to ToastNotifier."""

    def __init__(self):
        RULES_DIR.mkdir(parents=True, exist_ok=True)
        QUEUE_PATH.parent.mkdir(parents=True, exist_ok=True)
        self._toaster = ToastNotifier()
        self._notif_mgr = NotificationManager()

    def _path_for(self, rule_name: str) -> Path:
        safe = "".join(c for c in rule_name if c.isalnum() or c in ("_", "-"))[:100]
        return RULES_DIR / f"{safe}.json"

    def save_rule(
        self,
        rule_name: str,
        quiet_hours_start: str = "22:00",
        quiet_hours_end: str = "07:00",
        min_priority_during_quiet_hours: str = "urgent",
        suppress_during_focus_assist: bool = True,
    ) -> Dict:
        """Save a named quiet-hours/priority rule. During
        [quiet_hours_start, quiet_hours_end) (HH:MM, may wrap past
        midnight), only notifications at or above
        min_priority_during_quiet_hours are shown; everything else is
        queued. If suppress_during_focus_assist is True, any
        Focus Assist mode other than 'off' also holds back anything
        below 'urgent', independent of the quiet-hours window."""
        if not rule_name:
            return {"error": "rule_name must be non-empty"}
        if min_priority_during_quiet_hours not in _PRIORITY_ORDER:
            return {"error": f"min_priority_during_quiet_hours must be one of {list(_PRIORITY_ORDER)}"}
        rule = {
            "rule_name": rule_name,
            "quiet_hours_start": quiet_hours_start,
            "quiet_hours_end": quiet_hours_end,
            "min_priority_during_quiet_hours": min_priority_during_quiet_hours,
            "suppress_during_focus_assist": suppress_during_focus_assist,
        }
        try:
            self._path_for(rule_name).write_text(json.dumps(rule, indent=2), encoding="utf-8")
        except Exception as e:
            return {"error": str(e)}
        return {"success": True, "rule": rule}

    def list_rules(self) -> Dict:
        """List all saved notification rules."""
        try:
            rules = []
            for p in sorted(RULES_DIR.glob("*.json")):
                try:
                    rules.append(json.loads(p.read_text(encoding="utf-8")))
                except Exception:
                    continue
            return {"success": True, "rules": rules, "count": len(rules)}
        except Exception as e:
            return {"error": str(e)}

    def get_rule(self, rule_name: str) -> Dict:
        """View one saved notification rule."""
        path = self._path_for(rule_name)
        if not path.exists():
            return {"error": f"No rule named '{rule_name}'"}
        try:
            return {"success": True, "rule": json.loads(path.read_text(encoding="utf-8"))}
        except Exception as e:
            return {"error": str(e)}

    def delete_rule(self, rule_name: str) -> Dict:
        """Delete a saved notification rule."""
        path = self._path_for(rule_name)
        if not path.exists():
            return {"error": f"No rule named '{rule_name}'"}
        path.unlink()
        return {"success": True, "rule_name": rule_name, "deleted": True}

    def _in_quiet_hours(self, start: str, end: str) -> bool:
        now = _time.strftime("%H:%M")
        if start <= end:
            return start <= now < end
        return now >= start or now < end  # window wraps past midnight

    def _focus_assist_active(self) -> bool:
        result = self._notif_mgr.get_focus_assist_mode()
        if "error" in result:
            return False
        return result.get("mode") not in (None, "off", "unknown")

    def route(
        self, title: str, message: str, priority: str = "normal", rule_name: Optional[str] = None, duration: int = 5
    ) -> Dict:
        """Decide whether to show, queue, or drop a notification right
        now. Returns {action: 'shown'|'queued', ...}. With no
        rule_name, falls back to a built-in default (22:00-07:00 quiet
        hours, 'urgent' minimum, Focus Assist suppresses)."""
        if priority not in _PRIORITY_ORDER:
            return {"error": f"priority must be one of {list(_PRIORITY_ORDER)}"}
        rule = {
            "quiet_hours_start": "22:00",
            "quiet_hours_end": "07:00",
            "min_priority_during_quiet_hours": "urgent",
            "suppress_during_focus_assist": True,
        }
        if rule_name:
            fetched = self.get_rule(rule_name)
            if "error" in fetched:
                return fetched
            rule = fetched["rule"]

        held_back = False
        reason = None
        if (
            rule.get("suppress_during_focus_assist")
            and self._focus_assist_active()
            and _PRIORITY_ORDER[priority] < _PRIORITY_ORDER["urgent"]
        ):
            held_back, reason = True, "focus_assist_active"
        elif (
            self._in_quiet_hours(rule["quiet_hours_start"], rule["quiet_hours_end"])
            and _PRIORITY_ORDER[priority] < _PRIORITY_ORDER[rule["min_priority_during_quiet_hours"]]
        ):
            held_back, reason = True, "quiet_hours"

        if held_back:
            self._enqueue(title, message, priority)
            return {"success": True, "action": "queued", "reason": reason}

        show_result = self._toaster.show_notification(title, message, duration)
        return {"success": True, "action": "shown", "toast": show_result}

    def _enqueue(self, title: str, message: str, priority: str):
        queue = self._read_queue()
        queue.append({"title": title, "message": message, "priority": priority, "queued_at": _time.time()})
        QUEUE_PATH.write_text(json.dumps(queue, indent=2), encoding="utf-8")

    def _read_queue(self) -> List[Dict]:
        if not QUEUE_PATH.exists():
            return []
        try:
            return json.loads(QUEUE_PATH.read_text(encoding="utf-8"))
        except Exception:
            return []

    def get_queued(self) -> Dict:
        """List notifications currently held back, waiting for a flush."""
        return {"success": True, "queued": self._read_queue()}

    def clear_queue(self) -> Dict:
        """Discard everything currently queued without showing it."""
        QUEUE_PATH.write_text("[]", encoding="utf-8")
        return {"success": True, "cleared": True}

    def flush_queued(self, duration: int = 5) -> Dict:
        """Show every currently-queued notification now (e.g. once
        quiet hours end or Focus Assist is turned off), highest
        priority first, then clear the queue."""
        queue = sorted(self._read_queue(), key=lambda n: _PRIORITY_ORDER.get(n["priority"], 0), reverse=True)
        shown = []
        for n in queue:
            result = self._toaster.show_notification(n["title"], n["message"], duration)
            shown.append({"title": n["title"], "toast": result})
        QUEUE_PATH.write_text("[]", encoding="utf-8")
        return {"success": True, "shown_count": len(shown), "shown": shown}
