"""App launcher
============
Thin, explicit "launcher" entry point for windows/apps/manager.py's
AppManager (open/close/find/list-running apps).

AppManager itself is NOT renamed/moved here: it's imported directly
by six other modules across the project (skills/app_control/*.py,
skills/windows/manager.py, apps/base_app.py), so physically moving it
would mean touching every one of those call sites for a purely
cosmetic rename - real risk for zero behavior change. Instead this
module gives Phase 8's windows/apps/launcher.py path a real class to
import (AppLauncher), aliased directly to AppManager, so both names
resolve to the exact same, single implementation - no duplicated
logic, nothing to drift out of sync.
"""

from windows.apps.manager import AppManager, APP_ALIASES, HAS_PSUTIL, HAS_PYGETWINDOW, HAS_WINREG

# Same class, launcher-facing name for Phase 8's module layout.
AppLauncher = AppManager

__all__ = ["AppLauncher", "AppManager", "APP_ALIASES", "HAS_PSUTIL", "HAS_PYGETWINDOW", "HAS_WINREG"]
