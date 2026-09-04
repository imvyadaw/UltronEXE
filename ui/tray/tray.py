"""
System tray icon
=================
A Windows system-tray icon so Ultron shows up somewhere when it's running
instead of only a terminal window. Runs on its own background thread -
main.py's REPL loop is untouched. Subscribes to core.events to reflect
live status (idle/listening/thinking/speaking/tool) in the icon color,
tooltip, and menu, without main.py needing to know the tray exists.

Requires: pystray, Pillow (Pillow is already in requirements.txt for
screenshots; pystray is added alongside it). If pystray isn't installed,
get_tray() returns None and callers just skip the tray - same
"missing optional package degrades one feature, not the app" pattern
used throughout Ultron.
"""

import threading
from typing import Optional

try:
    import pystray
    from PIL import Image, ImageDraw

    HAS_PYSTRAY = True
except Exception:
    # Catches more than just ImportError: pystray picks a backend (win32 on
    # Windows, appindicator/GTK or Xorg elsewhere) at import time, and that
    # selection itself can raise on a machine with no display backend
    # available. Either way, the tray is just unavailable - not a crash.
    HAS_PYSTRAY = False

from core.events import get_event_bus
from core.logger import get_logger

logger = get_logger("ultron.ui.tray")

STATE_COLORS = {
    "idle": (110, 118, 129),
    "listening": (88, 166, 255),
    "thinking": (210, 153, 34),
    "speaking": (63, 185, 80),
    "tool": (88, 166, 255),
    "error": (248, 81, 73),
}


def _make_icon_image(color):
    """Draw a simple round 'J' badge in the given RGB color - no .ico file
    needed, so the tray works right out of a fresh checkout."""
    size = 64
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.ellipse((2, 2, size - 2, size - 2), fill=color)
    draw.text((size / 2 - 6, size / 2 - 14), "J", fill="white")
    return img


class UltronTray:
    """System tray icon reflecting Ultron's live status."""

    def __init__(self, on_exit=None, on_open_dashboard=None):
        if not HAS_PYSTRAY:
            raise ImportError("pystray/Pillow not installed - run: pip install pystray Pillow")

        self._on_exit = on_exit
        self._on_open_dashboard = on_open_dashboard
        self._state = "idle"
        self._thread: Optional[threading.Thread] = None

        self.icon = pystray.Icon(
            "ultron",
            icon=_make_icon_image(STATE_COLORS["idle"]),
            title="ULTRON - Idle",
            menu=self._build_menu(),
        )

        bus = get_event_bus()
        bus.subscribe("thinking_start", lambda **kw: self._set_state("thinking"))
        bus.subscribe("wake_detected", lambda **kw: self._set_state("listening"))
        bus.subscribe("speaking_start", lambda **kw: self._set_state("speaking"))
        bus.subscribe("speaking_end", lambda **kw: self._set_state("idle"))
        bus.subscribe("response_ready", lambda **kw: self._set_state("idle"))
        bus.subscribe("tool_executed", lambda **kw: self._flash_tool(kw.get("name", "")))
        bus.subscribe("error", lambda **kw: self._on_error(kw.get("text", ""), kw.get("source", "")))

    def _build_menu(self):
        return pystray.Menu(
            pystray.MenuItem(lambda item: f"Status: {self._state.capitalize()}", None, enabled=False),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Open Dashboard", self._open_dashboard, default=True),
            pystray.MenuItem("Open Logs Folder", self._open_logs),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Exit Ultron", self._exit),
        )

    def _refresh_icon(self):
        self.icon.icon = _make_icon_image(STATE_COLORS.get(self._state, STATE_COLORS["idle"]))
        self.icon.title = f"ULTRON - {self._state.capitalize()}"
        try:
            self.icon.update_menu()
        except Exception:
            from core.error_trace import log_swallowed as _lsw

            _lsw("ui.tray.tray._refresh_icon")

    def _set_state(self, state: str):
        self._state = state
        self._refresh_icon()

    def _flash_tool(self, name: str):
        self.icon.title = f"ULTRON - running {name}"
        try:
            self.icon.update_menu()
        except Exception:
            from core.error_trace import log_swallowed as _lsw

            _lsw("ui.tray.tray._flash_tool")

    def _on_error(self, text: str, source: str = ""):
        """Phase 13: reflect ui.notifications-raised errors in the tray -
        red icon plus, where the pystray backend supports it (Windows
        toast, GTK/appindicator notify), an OS-level balloon. notify()
        isn't implemented on every backend; degrades to icon-only, same
        "missing feature, not a crash" philosophy as the rest of this
        module."""
        self._set_state("error")
        try:
            self.icon.notify(text or "Ultron hit an error", f"ULTRON - {source or 'error'}")
        except Exception:
            from core.error_trace import log_swallowed as _lsw

            _lsw("ui.tray.tray._on_error")
        threading.Timer(6.0, lambda: self._recover_from_error()).start()

    def _recover_from_error(self):
        if self._state == "error":
            self._set_state("idle")

    def _open_dashboard(self, icon=None, item=None):
        if self._on_open_dashboard:
            self._on_open_dashboard()
        else:
            # Web dashboard (browser tab, live CPU/RAM + conversation feed)
            # replaced the old Tk window as the default - see
            # ui/web_dashboard/app.py.
            from ui.web_dashboard.app import open_dashboard

            open_dashboard()

    def _open_logs(self, icon=None, item=None):
        try:
            from windows import get_system_tools
            from config import LOGS_DIR

            get_system_tools().open_explorer(str(LOGS_DIR))
        except Exception as e:
            logger.error(f"Could not open logs folder: {e}")

    def _exit(self, icon=None, item=None):
        logger.info("Ultron exited via tray icon")
        icon.stop()
        if self._on_exit:
            try:
                self._on_exit()
            except Exception:
                from core.error_trace import log_swallowed as _lsw

                _lsw("ui.tray.tray._exit")
        # main.py's REPL loop blocks on input(), so it can't be woken from
        # a background thread cleanly without moving stdin reading to its
        # own thread too (a bigger refactor). A hard process exit here is
        # the honest, simple choice for v1 - the same tradeoff other
        # tray+console combo apps make.
        import os

        os._exit(0)

    def start(self) -> threading.Thread:
        """Run the tray icon on a background daemon thread."""
        self._thread = threading.Thread(target=self.icon.run, daemon=True, name="ultron-tray")
        self._thread.start()
        return self._thread


_tray: Optional[UltronTray] = None


def get_tray(on_exit=None, on_open_dashboard=None) -> Optional[UltronTray]:
    """Process-wide singleton. Returns None (never raises) if pystray isn't
    installed, so main.py can skip the tray gracefully."""
    global _tray
    if _tray is None:
        if not HAS_PYSTRAY:
            logger.warning("Tray icon unavailable - run: pip install pystray Pillow")
            return None
        _tray = UltronTray(on_exit=on_exit, on_open_dashboard=on_open_dashboard)
    return _tray


class TrayIcon:
    """Kept for import-compatibility with the original scaffolding
    (`ui.tray.tray.TrayIcon().launch()`)."""

    def launch(self, *args, **kwargs):
        tray = get_tray()
        if tray is None:
            raise ImportError("pystray/Pillow not installed - run: pip install pystray Pillow")
        return tray.start()
