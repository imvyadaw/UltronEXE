"""Window manager
==============
Move, resize, snap, minimize/maximize/restore, and enumerate windows
by title - the generic window-geometry counterpart to
windows/apps/manager.py (which manages *applications*, not window
placement) and browser/*/*.py (which only control browser windows
specifically).
"""

from typing import Dict, List

try:
    import pygetwindow as gw

    HAS_PYGETWINDOW = True
except ImportError:
    HAS_PYGETWINDOW = False

try:
    import ctypes

    HAS_CTYPES = True
    _user32 = ctypes.windll.user32 if hasattr(ctypes, "windll") else None
except Exception:
    HAS_CTYPES = False
    _user32 = None

# Screen-edge snap zones as fractions of the primary screen's size.
_SNAP_ZONES = {
    "left": (0, 0, 0.5, 1.0),
    "right": (0.5, 0, 0.5, 1.0),
    "top": (0, 0, 1.0, 0.5),
    "bottom": (0, 0.5, 1.0, 0.5),
    "top_left": (0, 0, 0.5, 0.5),
    "top_right": (0.5, 0, 0.5, 0.5),
    "bottom_left": (0, 0.5, 0.5, 0.5),
    "bottom_right": (0.5, 0.5, 0.5, 0.5),
    "full": (0, 0, 1.0, 1.0),
}


class WindowManager:
    """Find, move, resize, snap, and change the state of open windows."""

    def _find(self, window_title: str):
        if not HAS_PYGETWINDOW:
            return None
        query = window_title.lower()
        matches = [w for w in gw.getAllWindows() if w.title.strip() and query in w.title.lower()]
        return matches[0] if matches else None

    def list_windows(self) -> Dict:
        """List every open window with its title and geometry."""
        if not HAS_PYGETWINDOW:
            return {"error": "pygetwindow not installed - run: pip install pygetwindow"}
        try:
            windows = [w for w in gw.getAllWindows() if w.title.strip()]
            return {
                "count": len(windows),
                "windows": [
                    {
                        "title": w.title,
                        "left": w.left,
                        "top": w.top,
                        "width": w.width,
                        "height": w.height,
                        "minimized": w.isMinimized,
                        "maximized": w.isMaximized,
                    }
                    for w in windows
                ],
            }
        except Exception as e:
            return {"error": str(e)}

    def get_window_geometry(self, window_title: str) -> Dict:
        win = self._find(window_title)
        if not win:
            return {"error": f"No window matching '{window_title}'"}
        return {
            "title": win.title,
            "left": win.left,
            "top": win.top,
            "width": win.width,
            "height": win.height,
            "minimized": win.isMinimized,
            "maximized": win.isMaximized,
        }

    def move_window(self, window_title: str, x: int, y: int) -> Dict:
        win = self._find(window_title)
        if not win:
            return {"error": f"No window matching '{window_title}'"}
        try:
            win.moveTo(x, y)
            return {"success": True, "title": win.title, "left": x, "top": y}
        except Exception as e:
            return {"error": str(e)}

    def resize_window(self, window_title: str, width: int, height: int) -> Dict:
        win = self._find(window_title)
        if not win:
            return {"error": f"No window matching '{window_title}'"}
        try:
            win.resizeTo(width, height)
            return {"success": True, "title": win.title, "width": width, "height": height}
        except Exception as e:
            return {"error": str(e)}

    def set_window_bounds(self, window_title: str, x: int, y: int, width: int, height: int) -> Dict:
        """Move and resize in one call."""
        win = self._find(window_title)
        if not win:
            return {"error": f"No window matching '{window_title}'"}
        try:
            win.moveTo(x, y)
            win.resizeTo(width, height)
            return {"success": True, "title": win.title, "left": x, "top": y, "width": width, "height": height}
        except Exception as e:
            return {"error": str(e)}

    def snap_window(self, window_title: str, zone: str) -> Dict:
        """Snap a window to a screen zone: left, right, top, bottom,
        top_left, top_right, bottom_left, bottom_right, full."""
        if zone not in _SNAP_ZONES:
            return {"error": f"Unknown zone '{zone}'", "valid_zones": list(_SNAP_ZONES.keys())}
        win = self._find(window_title)
        if not win:
            return {"error": f"No window matching '{window_title}'"}
        try:
            import pyautogui

            screen_w, screen_h = pyautogui.size()
            fx, fy, fw, fh = _SNAP_ZONES[zone]
            x, y = int(fx * screen_w), int(fy * screen_h)
            w, h = int(fw * screen_w), int(fh * screen_h)
            if win.isMaximized:
                win.restore()
            win.moveTo(x, y)
            win.resizeTo(w, h)
            return {"success": True, "title": win.title, "zone": zone, "left": x, "top": y, "width": w, "height": h}
        except Exception as e:
            return {"error": str(e)}

    def minimize_window(self, window_title: str) -> Dict:
        win = self._find(window_title)
        if not win:
            return {"error": f"No window matching '{window_title}'"}
        win.minimize()
        return {"success": True, "title": win.title, "state": "minimized"}

    def maximize_window(self, window_title: str) -> Dict:
        win = self._find(window_title)
        if not win:
            return {"error": f"No window matching '{window_title}'"}
        win.maximize()
        return {"success": True, "title": win.title, "state": "maximized"}

    def restore_window(self, window_title: str) -> Dict:
        win = self._find(window_title)
        if not win:
            return {"error": f"No window matching '{window_title}'"}
        win.restore()
        return {"success": True, "title": win.title, "state": "restored"}

    def close_window(self, window_title: str) -> Dict:
        win = self._find(window_title)
        if not win:
            return {"error": f"No window matching '{window_title}'"}
        try:
            win.close()
            return {"success": True, "title": win.title, "state": "closed"}
        except Exception as e:
            return {"error": str(e)}

    def bring_to_front(self, window_title: str) -> Dict:
        win = self._find(window_title)
        if not win:
            return {"error": f"No window matching '{window_title}'"}
        try:
            if win.isMinimized:
                win.restore()
            win.activate()
            return {"success": True, "title": win.title, "state": "focused"}
        except Exception as e:
            return {"error": str(e)}

    def tile_windows(self, window_titles: List[str]) -> Dict:
        """Tile several windows side by side across the screen width."""
        if not HAS_PYGETWINDOW:
            return {"error": "pygetwindow not installed - run: pip install pygetwindow"}
        try:
            import pyautogui

            screen_w, screen_h = pyautogui.size()
            n = len(window_titles)
            if n == 0:
                return {"error": "No window titles given"}
            slice_w = screen_w // n
            results = []
            for i, title in enumerate(window_titles):
                win = self._find(title)
                if not win:
                    results.append({"title": title, "error": "not found"})
                    continue
                if win.isMaximized:
                    win.restore()
                win.moveTo(i * slice_w, 0)
                win.resizeTo(slice_w, screen_h)
                results.append({"title": win.title, "left": i * slice_w, "width": slice_w})
            return {"success": True, "tiled": results}
        except Exception as e:
            return {"error": str(e)}
