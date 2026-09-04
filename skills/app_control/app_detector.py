"""App detector
============
Answers "is X installed?" / "is X running?" / "what's currently
focused?" - the read-only counterpart to app_launcher.py. Combines
Start Menu shortcuts, the running process list (psutil) and the
foreground window (pygetwindow) to give a single trustworthy state
check instead of the caller having to know which source to trust.
"""

from typing import Dict, List

from windows.apps.manager import get_app_manager, HAS_PSUTIL, HAS_PYGETWINDOW

if HAS_PSUTIL:
    import psutil
if HAS_PYGETWINDOW:
    import pygetwindow as gw


class AppDetector:
    """Installed / running / focused-window detection for applications."""

    def __init__(self):
        self._apps = get_app_manager()

    def is_installed(self, app_name: str) -> Dict:
        """Check whether an app appears to be installed (Start Menu shortcut
        or Windows App Paths registry entry)."""
        try:
            found = self._apps.find_app(app_name) is not None
            if not found:
                found = self._apps._find_via_app_paths_registry(app_name) is not None
            return {"app_name": app_name, "installed": found}
        except Exception as e:
            return {"error": str(e)}

    def is_running(self, app_name: str) -> Dict:
        """Check whether a process matching app_name is currently running."""
        if not HAS_PSUTIL:
            return {"error": "psutil not installed - run: pip install psutil"}
        try:
            query_lower = app_name.lower().replace(" ", "")
            for proc in psutil.process_iter(["name"]):
                pname = (proc.info.get("name") or "").lower()
                if query_lower in pname.replace(" ", ""):
                    return {"app_name": app_name, "running": True, "process_name": proc.info["name"]}
            return {"app_name": app_name, "running": False}
        except Exception as e:
            return {"error": str(e)}

    def get_app_info(self, app_name: str) -> Dict:
        """Combined installed/running snapshot for one app."""
        installed = self.is_installed(app_name)
        running = self.is_running(app_name)
        return {
            "app_name": app_name,
            "installed": installed.get("installed", False),
            "running": running.get("running", False),
            "process_name": running.get("process_name"),
        }

    def detect_all_running(self) -> Dict:
        """List every currently running process with a visible name, plus
        window titles where available."""
        try:
            processes: List[Dict] = []
            if HAS_PSUTIL:
                seen = set()
                for proc in psutil.process_iter(["pid", "name", "memory_info"]):
                    name = proc.info.get("name")
                    if not name or name in seen:
                        continue
                    seen.add(name)
                    mem = proc.info.get("memory_info")
                    processes.append(
                        {
                            "pid": proc.info.get("pid"),
                            "name": name,
                            "memory_mb": round(mem.rss / (1024 * 1024), 1) if mem else None,
                        }
                    )
            windows = []
            if HAS_PYGETWINDOW:
                windows = [t for t in gw.getAllTitles() if t.strip()]
            return {"process_count": len(processes), "processes": processes, "window_titles": windows}
        except Exception as e:
            return {"error": str(e)}

    def get_focused_app(self) -> Dict:
        """Get the title (and best-guess process) of the currently focused window."""
        if not HAS_PYGETWINDOW:
            return {"error": "pygetwindow not installed - run: pip install pygetwindow"}
        try:
            active = gw.getActiveWindow()
            if not active:
                return {"focused": False}
            return {"focused": True, "title": active.title, "width": active.width, "height": active.height}
        except Exception as e:
            return {"error": str(e)}
