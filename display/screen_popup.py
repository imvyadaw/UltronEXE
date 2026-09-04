"""
Screen Popup
============
The simplest possible notification surface: a short-lived tkinter
window with a message, auto-closing after a few seconds. tkinter ships
with most Python installs but still needs an actual display (X11/
Wayland/Windows/macOS session) - on a headless box, or in a test run,
show() falls back to appending the message to an in-memory log instead
of raising, same "hardware/environment not there yet" contract every
other module in this phase already honors.

Deliberately not a queue/daemon - one popup, one call, blocks briefly
(auto_close_seconds) then returns. A caller wanting several queued
popups should call show() several times; this module doesn't manage
scheduling.
"""

import time
from typing import Dict, List, Optional

try:
    import tkinter as tk

    _TK_AVAILABLE = True
except Exception:
    _TK_AVAILABLE = False

DEFAULT_AUTO_CLOSE_SECONDS = 4


class ScreenPopup:
    """Best-effort on-screen notification. Use get_screen_popup()."""

    def __init__(self):
        self._log: List[Dict] = []

    def is_available(self) -> bool:
        return _TK_AVAILABLE

    def show(self, message: str, title: str = "Ultron", auto_close_seconds: int = DEFAULT_AUTO_CLOSE_SECONDS) -> bool:
        """Returns True if an actual window was shown, False if it
        fell back to the in-memory log (no display available, or
        tkinter itself failed to init - both logged the same way so a
        caller checking return value doesn't need to know which)."""
        entry = {"title": title, "message": message, "logged_at": time.time()}
        self._log.append(entry)

        if not _TK_AVAILABLE:
            return False
        try:
            root = tk.Tk()
            root.title(title)
            root.attributes("-topmost", True)
            tk.Label(root, text=message, padx=20, pady=20, wraplength=320).pack()
            root.after(auto_close_seconds * 1000, root.destroy)
            root.mainloop()
            return True
        except Exception:
            return False

    def recent(self, limit: int = 20) -> List[Dict]:
        return self._log[-limit:]


_screen_popup: Optional[ScreenPopup] = None


def get_screen_popup() -> ScreenPopup:
    global _screen_popup
    if _screen_popup is None:
        _screen_popup = ScreenPopup()
    return _screen_popup
