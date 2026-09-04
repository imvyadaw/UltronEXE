"""
Alerts
======
Rule-based alerting on top of monitoring/resource_monitor.py and
monitoring/health_check.py - "notify me if CPU stays above 90% for a
while" instead of just exposing raw numbers. Delivers via
windows/notifications/toasts.py (the same toast notifications
Ultron already uses elsewhere) so an alert firing looks and feels like
any other Ultron notification, and logs every fired alert to
security/audit.py so there's a record even if the toast is missed.

Rules are simple callables over a snapshot dict, not a full expression
language - keeps this readable and matches the rest of the codebase's
preference for plain Python over config-driven DSLs (see e.g.
core/permissions.py's plain DESTRUCTIVE_TOOLS set).
"""

import time
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

from monitoring.resource_monitor import get_resource_monitor
from monitoring.health_check import run_health_check

try:
    from windows.notifications.toasts import ToastNotifier

    HAS_NOTIFICATIONS = True
except ImportError:
    HAS_NOTIFICATIONS = False

try:
    from security.audit import get_audit_log

    HAS_AUDIT = True
except ImportError:
    HAS_AUDIT = False


@dataclass
class AlertRule:
    name: str
    # Given a resource snapshot dict (see monitoring/resource_monitor.py's
    # snapshot() shape), return True if this rule should fire.
    condition: Callable[[Dict], bool]
    message: str
    # Don't re-fire the same alert more often than this, even if the
    # condition stays true on every check - avoids a notification storm
    # for a sustained high-CPU period.
    cooldown_seconds: int = 300
    last_fired_at: float = field(default=0.0, repr=False)


def _default_rules() -> List[AlertRule]:
    return [
        AlertRule(
            name="high_cpu",
            condition=lambda s: s.get("cpu_percent", 0) >= 90,
            message="CPU usage is above 90%",
        ),
        AlertRule(
            name="high_memory",
            condition=lambda s: s.get("memory_percent", 0) >= 90,
            message="Memory usage is above 90%",
        ),
        AlertRule(
            name="low_disk",
            condition=lambda s: s.get("disk_percent", 0) >= 90,
            message="Disk usage is above 90% - low free space",
        ),
    ]


class AlertManager:
    """Evaluate alert rules against current resource usage and notify on trigger."""

    def __init__(self, rules: Optional[List[AlertRule]] = None):
        self.rules = rules if rules is not None else _default_rules()
        self._notifications = ToastNotifier() if HAS_NOTIFICATIONS else None
        self._audit = get_audit_log() if HAS_AUDIT else None
        self._fired_log: List[Dict] = []

    def add_rule(self, rule: AlertRule) -> None:
        self.rules.append(rule)

    def check_now(self, notify: bool = True) -> Dict:
        """Run every rule once against a fresh resource snapshot. Returns
        which rules fired (respecting cooldown)."""
        try:
            snapshot = get_resource_monitor().snapshot()
            if "error" in snapshot:
                return {"error": snapshot["error"]}

            fired = []
            now = time.time()
            for rule in self.rules:
                try:
                    triggered = rule.condition(snapshot)
                except Exception:
                    continue  # a broken rule shouldn't stop the others from evaluating

                if triggered and (now - rule.last_fired_at) >= rule.cooldown_seconds:
                    rule.last_fired_at = now
                    fired.append({"name": rule.name, "message": rule.message})
                    self._fired_log.append({"name": rule.name, "message": rule.message, "fired_at": now})

                    if notify and self._notifications:
                        self._notifications.show_notification("Ultron alert", rule.message)
                    if self._audit:
                        self._audit.record("alert_fired", {"rule": rule.name, "message": rule.message})

            return {"checked_at": now, "snapshot": snapshot, "fired": fired}
        except Exception as e:
            return {"error": str(e)}

    def check_health(self, notify: bool = True) -> Dict:
        """Same idea as check_now(), but over monitoring/health_check.py's
        broader checks (internet, storage) instead of just resource numbers."""
        try:
            result = run_health_check()
            if not result["healthy"] and notify and self._notifications:
                failing = [c["name"] for c in result["checks"] if not c.get("healthy")]
                self._notifications.show_notification("Ultron health check failed", f"Issues: {', '.join(failing)}")
            return result
        except Exception as e:
            return {"error": str(e)}

    def recent_alerts(self, limit: int = 20) -> Dict:
        return {"alerts": self._fired_log[-limit:][::-1]}


_manager: Optional[AlertManager] = None


def get_alert_manager() -> AlertManager:
    global _manager
    if _manager is None:
        _manager = AlertManager()
    return _manager
