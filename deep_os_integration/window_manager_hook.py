"""
window_manager_hook.py
=======================
Tracks the foreground window and lets ULTRON enumerate, focus, move,
resize and snap windows - the automation layer behind things like
"snap this to the left half" or "what am I looking at right now".

Dependencies: pip install pywin32
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from typing import Callable, List, Optional

import win32gui
import win32con
import win32process
import psutil

logger = logging.getLogger("ultron.window_manager_hook")


@dataclass
class WindowInfo:
    hwnd: int
    title: str
    process_name: Optional[str]
    rect: tuple  # (left, top, right, bottom)
    is_minimized: bool


class WindowManagerHook:
    def __init__(self, poll_interval: float = 0.5):
        self.poll_interval = poll_interval
        self._last_foreground: Optional[int] = None
        self._on_foreground_change: Optional[Callable[[WindowInfo], None]] = None
        self._thread: Optional[threading.Thread] = None
        self._running = False

    # --------------------------------------------------------- inspection
    def _window_info(self, hwnd: int) -> WindowInfo:
        title = win32gui.GetWindowText(hwnd)
        rect = win32gui.GetWindowRect(hwnd)
        is_min = win32gui.IsIconic(hwnd)
        proc_name = None
        try:
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            proc_name = psutil.Process(pid).name()
        except Exception:
            from core.error_trace import log_swallowed as _lsw

            _lsw("deep_os_integration.window_manager_hook._window_info")
        return WindowInfo(hwnd=hwnd, title=title, process_name=proc_name, rect=rect, is_minimized=is_min)

    def list_windows(self, visible_only: bool = True) -> List[WindowInfo]:
        windows = []

        def _enum_handler(hwnd, _):
            if visible_only and not win32gui.IsWindowVisible(hwnd):
                return
            title = win32gui.GetWindowText(hwnd)
            if title.strip():
                windows.append(self._window_info(hwnd))

        win32gui.EnumWindows(_enum_handler, None)
        return windows

    def get_foreground(self) -> Optional[WindowInfo]:
        hwnd = win32gui.GetForegroundWindow()
        if not hwnd:
            return None
        return self._window_info(hwnd)

    def find_by_title(self, substring: str) -> List[WindowInfo]:
        sub = substring.lower()
        return [w for w in self.list_windows() if sub in w.title.lower()]

    # ---------------------------------------------------------- actions
    def focus(self, hwnd: int) -> bool:
        try:
            if win32gui.IsIconic(hwnd):
                win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
            win32gui.SetForegroundWindow(hwnd)
            return True
        except Exception as e:
            logger.error("focus(%s) failed: %s", hwnd, e)
            return False

    def minimize(self, hwnd: int):
        win32gui.ShowWindow(hwnd, win32con.SW_MINIMIZE)

    def maximize(self, hwnd: int):
        win32gui.ShowWindow(hwnd, win32con.SW_MAXIMIZE)

    def close(self, hwnd: int):
        win32gui.PostMessage(hwnd, win32con.WM_CLOSE, 0, 0)

    def move_resize(self, hwnd: int, x: int, y: int, width: int, height: int):
        win32gui.MoveWindow(hwnd, x, y, width, height, True)

    def snap(self, hwnd: int, position: str, screen_w: int, screen_h: int):
        """position: 'left' | 'right' | 'top' | 'bottom' | 'maximize'."""
        half_w, half_h = screen_w // 2, screen_h // 2
        layouts = {
            "left": (0, 0, half_w, screen_h),
            "right": (half_w, 0, half_w, screen_h),
            "top": (0, 0, screen_w, half_h),
            "bottom": (0, half_h, screen_w, half_h),
        }
        if position == "maximize":
            self.maximize(hwnd)
            return
        if position in layouts:
            self.move_resize(hwnd, *layouts[position])

    # ------------------------------------------------------ change events
    def on_foreground_change(self, callback: Callable[[WindowInfo], None]):
        self._on_foreground_change = callback

    def _poll_loop(self):
        while self._running:
            hwnd = win32gui.GetForegroundWindow()
            if hwnd and hwnd != self._last_foreground:
                self._last_foreground = hwnd
                if self._on_foreground_change:
                    self._on_foreground_change(self._window_info(hwnd))
            time.sleep(self.poll_interval)

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._poll_loop, daemon=True)
        self._thread.start()
        logger.info("WindowManagerHook watching foreground window changes")

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=2)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    wmh = WindowManagerHook()
    wmh.on_foreground_change(lambda w: print(f"Active: {w.title} ({w.process_name})"))
    wmh.start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        wmh.stop()
