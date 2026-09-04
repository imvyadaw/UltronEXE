"""
ui/widgets/desktop.py - alias for ui/widgets/widgets.py.

The real implementation lives in widgets.py; this file exists only so
the path `ui/widgets/desktop.py` from the originally requested project
tree also works, without maintaining two copies of the same code.

    from ui.widgets.desktop import TkWindow, StatusPill, StatCard, Toast
"""

from ui.widgets.widgets import (
    TkWindow,
    StatusPill,
    StatCard,
    ScrollingLog,
    Toast,
    NotificationFeed,
    Widget,
)

__all__ = [
    "TkWindow",
    "StatusPill",
    "StatCard",
    "ScrollingLog",
    "Toast",
    "NotificationFeed",
    "Widget",
]
