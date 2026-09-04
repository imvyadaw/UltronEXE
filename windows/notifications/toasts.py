"""Windows toast notifications
============================
Show native Windows toast notifications. Uses win11toast (works on
Windows 10/11) if installed, falling back to plyer, then to a plain
print so it never crashes if neither is available.

Renamed from notifications/notifications.py (NotificationTools) as
part of Phase 8's windows/ restructure. One external call site
(monitoring/alerts.py) also imports this class directly for alert
delivery and has been updated alongside this rename.
"""

from typing import Dict

try:
    from win11toast import toast as _win11_toast

    HAS_WIN11TOAST = True
except ImportError:
    HAS_WIN11TOAST = False

try:
    from plyer import notification as _plyer_notification

    HAS_PLYER = True
except ImportError:
    HAS_PLYER = False


class ToastNotifier:
    """Show native Windows toast notifications."""

    def show_notification(self, title: str, message: str, duration: int = 5) -> Dict:
        """Show a toast notification. Tries win11toast, then plyer, then a console fallback."""
        try:
            if HAS_WIN11TOAST:
                _win11_toast(title, message, duration="short" if duration <= 5 else "long")
                return {"success": True, "backend": "win11toast", "title": title}
            if HAS_PLYER:
                _plyer_notification.notify(title=title, message=message, timeout=duration)
                return {"success": True, "backend": "plyer", "title": title}
            print(f"[ULTRON NOTIFICATION] {title}: {message}")
            return {
                "success": True,
                "backend": "console",
                "note": "Install win11toast or plyer for real Windows toast popups: pip install win11toast",
            }
        except Exception as e:
            return {"error": str(e)}
