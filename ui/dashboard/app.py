"""
ui/dashboard/app.py - alias for ui/dashboard/dashboard.py.

The real implementation lives in dashboard.py (named for what it is,
a Dashboard class + open_dashboard()); this file exists only so the
path `ui/dashboard/app.py` from the originally requested project tree
also works, without maintaining two copies of the same code.

    from ui.dashboard.app import open_dashboard, Dashboard

does exactly the same thing as importing from ui.dashboard.dashboard.
"""

from ui.dashboard.dashboard import Dashboard, open_dashboard

__all__ = ["Dashboard", "open_dashboard"]
