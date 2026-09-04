"""
ui/tray/icon.py - alias for ui/tray/tray.py.

The real implementation lives in tray.py; this file exists only so
the path `ui/tray/icon.py` from the originally requested project tree
also works, without maintaining two copies of the same code.

    from ui.tray.icon import UltronTray, TrayIcon, get_tray
"""

from ui.tray.tray import UltronTray, TrayIcon, get_tray

__all__ = ["UltronTray", "TrayIcon", "get_tray"]
