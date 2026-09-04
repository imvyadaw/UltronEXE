"""App control manager
====================
High-level orchestrator that composes AppFinder + AppDetector +
AppLauncher with window-state actions (minimize/maximize/focus/close)
so callers don't have to juggle four objects for a single "manage this
app" request. This is the object skills/agents should import; the
other three files are the building blocks it's made of.
"""

from typing import Dict, List

from windows.apps.manager import get_app_manager, HAS_PYGETWINDOW
from skills.app_control.app_finder import AppFinder
from skills.app_control.app_detector import AppDetector
from skills.app_control.app_launcher import AppLauncher

if HAS_PYGETWINDOW:
    import pygetwindow as gw


class AppControlManager:
    """One-stop app control: find, detect, launch, and manage window state."""

    def __init__(self):
        self._apps = get_app_manager()
        self.finder = AppFinder()
        self.detector = AppDetector()
        self.launcher = AppLauncher()

    # --- pass-through convenience (kept flat for tool-dispatch friendliness) ---
    def open_app(self, app_name: str, args: List[str] = None, as_admin: bool = False) -> Dict:
        return self.launcher.launch(app_name, args=args, as_admin=as_admin)

    def close_app(self, app_name: str) -> Dict:
        return self._apps.close_application(app_name)

    def restart_app(self, app_name: str) -> Dict:
        return self.launcher.relaunch(app_name)

    def list_open_apps(self) -> Dict:
        return self._apps.list_running_apps()

    def find_app(self, query: str) -> Dict:
        return self.finder.find(query)

    def app_status(self, app_name: str) -> Dict:
        return self.detector.get_app_info(app_name)

    def list_by_category(self, category: str) -> Dict:
        """Passthrough to AppFinder.list_by_category() - windows/__init__.py's
        SystemTools.__getattr__ only resolves attributes that live directly on
        one of self._parts (self._app_control here), not on self._app_control's
        own nested .finder, so this was missing and the "list_apps_by_category"
        tool raised AttributeError until this passthrough was added (Phase 24
        execution audit)."""
        return self.finder.list_by_category(category)

    # --- window-state control on top of a running app's window ---
    def _matching_windows(self, app_name: str):
        if not HAS_PYGETWINDOW:
            return []
        query_lower = app_name.lower()
        return [w for w in gw.getAllWindows() if w.title.strip() and query_lower in w.title.lower()]

    def minimize_app(self, app_name: str) -> Dict:
        """Minimize every window belonging to an app."""
        if not HAS_PYGETWINDOW:
            return {"error": "pygetwindow not installed - run: pip install pygetwindow"}
        try:
            windows = self._matching_windows(app_name)
            if not windows:
                return {"success": False, "error": f"No open window found for '{app_name}'"}
            for w in windows:
                w.minimize()
            return {"success": True, "app_name": app_name, "windows_affected": len(windows)}
        except Exception as e:
            return {"error": str(e)}

    def maximize_app(self, app_name: str) -> Dict:
        """Maximize the first window belonging to an app."""
        if not HAS_PYGETWINDOW:
            return {"error": "pygetwindow not installed - run: pip install pygetwindow"}
        try:
            windows = self._matching_windows(app_name)
            if not windows:
                return {"success": False, "error": f"No open window found for '{app_name}'"}
            windows[0].maximize()
            return {"success": True, "app_name": app_name, "window_title": windows[0].title}
        except Exception as e:
            return {"error": str(e)}

    def focus_app(self, app_name: str) -> Dict:
        """Bring an app's window to the foreground, restoring it first if minimized."""
        if not HAS_PYGETWINDOW:
            return {"error": "pygetwindow not installed - run: pip install pygetwindow"}
        try:
            windows = self._matching_windows(app_name)
            if not windows:
                return {"success": False, "error": f"No open window found for '{app_name}'"}
            win = windows[0]
            if win.isMinimized:
                win.restore()
            win.activate()
            return {"success": True, "app_name": app_name, "window_title": win.title}
        except Exception as e:
            return {"error": str(e)}

    def close_all_by_category(self, category: str) -> Dict:
        """Close every running/installed app in a category (e.g. close all browsers)."""
        listing = self.finder.list_by_category(category)
        if "error" in listing:
            return listing
        results = [{"app_name": name, **self._apps.close_application(name)} for name in listing["apps"]]
        closed = sum(1 for r in results if r.get("success"))
        return {"category": category, "attempted": len(results), "closed": closed, "results": results}

    def kill_unresponsive_apps(self) -> Dict:
        """Force-close windows Windows itself has flagged as 'Not Responding'."""
        if not HAS_PYGETWINDOW:
            return {"error": "pygetwindow not installed - run: pip install pygetwindow"}
        try:
            candidates = [w for w in gw.getAllWindows() if "(Not Responding)" in w.title]
            killed = []
            for w in candidates:
                app_guess = w.title.split(" - ")[0].split(" (")[0]
                result = self._apps.close_application(app_guess)
                killed.append({"window_title": w.title, "result": result})
            return {"found": len(candidates), "killed": killed}
        except Exception as e:
            return {"error": str(e)}
