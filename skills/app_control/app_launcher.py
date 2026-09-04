"""App launcher
============
Launching beyond AppManager.open_application()'s single-shot
os.startfile(): pass command-line arguments, request an elevated
(admin) launch, launch several apps in one call, relaunch (close then
reopen), and optionally block until the app's window actually appears.
"""

import subprocess
import time
from typing import Dict, List, Optional

from windows.apps.manager import get_app_manager, HAS_PYGETWINDOW

if HAS_PYGETWINDOW:
    import pygetwindow as gw

try:
    import win32com.client  # pywin32, used only for the ShellExecute "runas" verb

    HAS_WIN32COM = True
except ImportError:
    HAS_WIN32COM = False


class AppLauncher:
    """Launch/relaunch applications with extra options AppManager doesn't cover."""

    def __init__(self):
        self._apps = get_app_manager()

    def launch(self, app_name: str, args: Optional[List[str]] = None, as_admin: bool = False) -> Dict:
        """Launch an app, optionally with command-line arguments or elevated."""
        try:
            if as_admin:
                return self._launch_as_admin(app_name, args or [])

            if args:
                # Need an actual executable path to pass args to - resolve via
                # the finder-style lookup AppManager already does internally.
                exe_path = None
                shortcut_name = self._apps.find_app(app_name)
                if shortcut_name:
                    shortcut_path = self._apps._shortcut_paths.get(shortcut_name)
                    exe_path = str(shortcut_path) if shortcut_path else None
                if not exe_path:
                    exe_path = self._apps._find_via_app_paths_registry(app_name)
                if not exe_path:
                    from skills.app_control.app_finder import AppFinder

                    exe_path = AppFinder().find_executable(app_name)
                if not exe_path:
                    return {
                        "success": False,
                        "error": f"Could not resolve an executable path for '{app_name}' to pass arguments",
                    }

                subprocess.Popen([exe_path, *args])
                return {"success": True, "opened": app_name, "args": args}

            return self._apps.open_application(app_name)
        except Exception as e:
            return {"error": str(e)}

    def _launch_as_admin(self, app_name: str, args: List[str]) -> Dict:
        if not HAS_WIN32COM:
            return {"error": "pywin32 not installed - run: pip install pywin32"}
        try:
            exe_path = self._apps._find_via_app_paths_registry(app_name)
            if not exe_path:
                from skills.app_control.app_finder import AppFinder

                exe_path = AppFinder().find_executable(app_name)
            if not exe_path:
                exe_path = app_name  # last resort, hope it's on PATH

            shell = win32com.client.Dispatch("Shell.Application")
            shell.ShellExecute(exe_path, " ".join(args), "", "runas", 1)
            return {"success": True, "opened": app_name, "elevated": True}
        except Exception as e:
            return {"error": str(e)}

    def launch_multiple(self, app_names: List[str]) -> Dict:
        """Open several apps back to back. Returns per-app results."""
        results = []
        for name in app_names:
            results.append({"app_name": name, **self._apps.open_application(name)})
        succeeded = sum(1 for r in results if r.get("success"))
        return {
            "success": succeeded == len(app_names),
            "results": results,
            "opened_count": succeeded,
            "total": len(app_names),
        }

    def launch_and_wait(self, app_name: str, timeout: float = 10.0) -> Dict:
        """Launch an app and block until a matching window title shows up
        (or timeout). Useful before automating clicks/typing into a fresh app."""
        open_result = self._apps.open_application(app_name)
        if not open_result.get("success"):
            return open_result
        if not HAS_PYGETWINDOW:
            return {
                **open_result,
                "window_found": None,
                "note": "pygetwindow not installed, could not confirm window appeared",
            }

        query_lower = app_name.lower()
        deadline = time.time() + timeout
        while time.time() < deadline:
            titles = gw.getAllTitles()
            for title in titles:
                if title.strip() and query_lower in title.lower():
                    return {**open_result, "window_found": True, "window_title": title}
            time.sleep(0.3)
        return {
            **open_result,
            "window_found": False,
            "note": f"No window matching '{app_name}' appeared within {timeout}s",
        }

    def relaunch(self, app_name: str) -> Dict:
        """Close an app (if running) and open it again fresh."""
        close_result = self._apps.close_application(app_name)
        time.sleep(1.0)
        open_result = self._apps.open_application(app_name)
        return {"closed": close_result, "opened": open_result}
