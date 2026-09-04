"""
Status overlay
===============
A small always-on-top, borderless status pill (bottom-right corner) that
shows what Ultron is doing right now - "Listening...", "Thinking...",
"[tool] open_application", "Speaking..." - then hides itself again a few
seconds after going idle. A purely visual aid on top of the terminal/voice
modes; nothing else depends on it, and Ultron behaves identically whether
or not the overlay is ever enabled. Runs on its own Tk thread (see
ui.widgets.widgets.TkWindow).
"""

from typing import Optional

from core.events import get_event_bus
from ui.widgets.widgets import TkWindow, BG_PANEL, FG

IDLE_HIDE_MS = 4000
ERROR_HIDE_MS = 8000  # errors stay up longer than a routine state - see notify()

STATE_TEXT = {
    "listening": "\U0001f3a4 Listening...",
    "thinking": "\U0001f4ad Thinking...",
    "speaking": "\U0001f50a Speaking...",
    "tool": "\u2699 Running tool...",
    "error": "\u26a0 Error",
}
STATE_COLOR = {
    "listening": "#58a6ff",
    "thinking": "#d29922",
    "speaking": "#3fb950",
    "tool": "#58a6ff",
    "error": "#f85149",
}

_window: Optional[TkWindow] = None
_wired = False


def _build(win: TkWindow, root):
    import tkinter as tk

    root.overrideredirect(True)  # borderless
    root.attributes("-topmost", True)  # always on top
    try:
        root.attributes("-alpha", 0.92)  # slight transparency (no-op if unsupported)
    except Exception:
        from core.error_trace import log_swallowed as _lsw

        _lsw("ui.overlay.overlay._build")
    root.configure(bg=BG_PANEL)

    win.label = tk.Label(
        root,
        text="",
        bg=BG_PANEL,
        fg=FG,
        font=("Consolas", 11, "bold"),
        padx=16,
        pady=8,
    )
    win.label.pack()
    win._hide_job = None

    sw = root.winfo_screenwidth()
    sh = root.winfo_screenheight()
    root.geometry(f"+{sw - 260}+{sh - 100}")
    root.withdraw()  # start hidden until the first event


def _hide(win: TkWindow):
    win.root.withdraw()


def _show_state(win: TkWindow, state: str, extra: str = ""):
    text = STATE_TEXT.get(state, "")
    if not text:
        _hide(win)
        return
    if extra:
        text = f"{text} ({extra})"
    win.label.config(text=text, fg=STATE_COLOR.get(state, FG))
    win.root.deiconify()
    win.root.lift()

    if win._hide_job:
        win.root.after_cancel(win._hide_job)
    hide_after = ERROR_HIDE_MS if state == "error" else IDLE_HIDE_MS
    win._hide_job = win.root.after(hide_after, lambda: _hide(win))


def _on_event(win: TkWindow, event: str, data: dict):
    if event == "show":
        _show_state(win, data.get("state", ""), data.get("extra", ""))
    elif event == "hide":
        _hide(win)


def _wire_events(win: TkWindow):
    global _wired
    if _wired:
        return
    _wired = True
    bus = get_event_bus()
    bus.subscribe("wake_detected", lambda **kw: win.post("show", state="listening"))
    bus.subscribe("thinking_start", lambda **kw: win.post("show", state="thinking"))
    bus.subscribe("tool_executed", lambda **kw: win.post("show", state="tool", extra=kw.get("name", "")))
    bus.subscribe("response_ready", lambda **kw: win.post("hide"))
    bus.subscribe("speaking_start", lambda **kw: win.post("show", state="speaking"))
    bus.subscribe("speaking_end", lambda **kw: win.post("hide"))
    bus.subscribe("error", lambda **kw: win.post("show", state="error", extra=(kw.get("text", "") or "")[:60]))


def enable_overlay() -> TkWindow:
    """Create the overlay window and wire it to core.events. Safe to call
    more than once (no-ops after the first)."""
    global _window
    if _window is None or not _window.is_alive():
        _window = TkWindow("UltronOverlay", build=_build, on_event=_on_event, size="240x60")
        _window.start()
        _window.wait_ready()
    _wire_events(_window)
    return _window


class Overlay:
    """Kept for import-compatibility with the original scaffolding
    (`ui.overlay.overlay.Overlay().show()`)."""

    def show(self, *args, **kwargs):
        return enable_overlay()
