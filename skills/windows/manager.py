"""
Windows management skill (Phase 4 facade)
===========================================
Combines windows/apps/manager.py (process-level open/close/list) with
windows/window_manager.py (window geometry/move/resize/snap/minimize/
maximize/close/tile) behind the common BaseSkill interface used by the
skill registry / AI tool layer.
"""

from skills.base_skill import BaseSkill
from windows.apps.manager import get_app_manager
from windows.window_manager import WindowManager


class WindowsManager(BaseSkill):
    """Open/close applications and control window position, size, and state."""

    name = "windows_manager"
    description = "Open/close applications and control window position, size, snapping, and state."
    category = "system"

    def __init__(self):
        self._apps = get_app_manager()
        self._windows = WindowManager()
        super().__init__()

    def register_actions(self) -> None:
        a, w = self._apps, self._windows
        self._actions = {
            "open_app": a.open_application,
            "close_app": a.close_application,
            "list_apps": a.list_running_apps,
            "list_windows": w.list_windows,
            "get_geometry": w.get_window_geometry,
            "move": w.move_window,
            "resize": w.resize_window,
            "set_bounds": w.set_window_bounds,
            "snap": w.snap_window,
            "minimize": w.minimize_window,
            "maximize": w.maximize_window,
            "restore": w.restore_window,
            "close_window": w.close_window,
            "bring_to_front": w.bring_to_front,
            "tile": w.tile_windows,
        }
