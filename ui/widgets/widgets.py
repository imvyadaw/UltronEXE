"""
Shared Tk widgets
==================
Small reusable tkinter widgets used by ui/dashboard and ui/overlay, plus
TkWindow: a helper that runs a Tk root + mainloop on its own background
thread. main.py's REPL (UltronRuntime.run_text etc.) blocks on input() on the main
thread, so any GUI window needs its own thread and its own Tk root - and
Tk widgets are not safe to touch from a thread other than the one running
their mainloop. TkWindow gives callers a thread-safe post(event, **data)
queue instead: EventBus handlers (which may fire from main.py's thread or
a mic/STT thread) call post(), and the Tk thread drains the queue on a
timer and applies the update itself.

Requires: tkinter (ships with the standard python.org Windows installer;
if it's missing, `python -m tkinter` will say so - reinstall Python with
that option checked).
"""

import queue
import threading
from typing import Callable, Optional

# Dark, terminal-style palette to match Ultron's colored-console look.
BG = "#0d1117"
BG_PANEL = "#161b22"
FG = "#c9d1d9"
FG_DIM = "#6e7681"
ACCENT = "#58a6ff"
GREEN = "#3fb950"
YELLOW = "#d29922"
RED = "#f85149"

STATE_COLORS = {
    "idle": FG_DIM,
    "listening": ACCENT,
    "thinking": YELLOW,
    "speaking": GREEN,
    "tool": ACCENT,
    "error": RED,
}


class TkWindow(threading.Thread):
    """Runs a Tk root + mainloop on its own daemon thread.

    `build(win, root)` is called once, on the Tk thread, to construct the
    widgets and stash whatever handles `on_event` will need as attributes
    on `win` (e.g. `win.log = ScrollingLog(root)`).

    `on_event(win, event, data)` is called on the Tk thread whenever
    something calls `win.post(event, **data)` from any thread - use it to
    apply the update to the widgets `build` created.
    """

    def __init__(self, title: str, build: Callable, on_event: Callable, size: str = "420x520"):
        super().__init__(daemon=True)
        self.title = title
        self._build = build
        self._on_event = on_event
        self._size = size
        self._queue: "queue.Queue" = queue.Queue()
        self._ready = threading.Event()
        self.root = None

    def post(self, event: str, **data):
        """Thread-safe: call this from any thread to push an update."""
        self._queue.put((event, data))

    def _drain(self):
        try:
            while True:
                event, data = self._queue.get_nowait()
                try:
                    self._on_event(self, event, data)
                except Exception:
                    from core.error_trace import log_swallowed as _lsw

                    _lsw("ui.widgets.widgets._drain")
        except queue.Empty:
            from core.error_trace import log_swallowed as _lsw

            _lsw("ui.widgets.widgets._drain")
        if self.root:
            self.root.after(200, self._drain)

    def run(self):
        import tkinter as tk

        self.root = tk.Tk()
        self.root.title(self.title)
        self.root.geometry(self._size)
        self.root.configure(bg=BG)
        self._build(self, self.root)
        self._ready.set()
        self.root.after(200, self._drain)
        self.root.mainloop()

    def wait_ready(self, timeout: float = 5.0):
        self._ready.wait(timeout)

    def close(self):
        if self.root:
            try:
                self.root.after(0, self.root.destroy)
            except Exception:
                from core.error_trace import log_swallowed as _lsw

                _lsw("ui.widgets.widgets.close")


class StatusPill:
    """A coloured dot + label showing Ultron's current state. Build inside
    a TkWindow.build() callback (needs a live Tk root)."""

    def __init__(self, parent):
        import tkinter as tk

        self.frame = tk.Frame(parent, bg=BG_PANEL)
        self._dot = tk.Canvas(self.frame, width=14, height=14, bg=BG_PANEL, highlightthickness=0)
        self._dot_id = self._dot.create_oval(2, 2, 12, 12, fill=FG_DIM, outline="")
        self._dot.pack(side="left", padx=(8, 4), pady=6)
        self._label = tk.Label(self.frame, text="Idle", bg=BG_PANEL, fg=FG, font=("Consolas", 10, "bold"))
        self._label.pack(side="left", padx=(0, 8))

    def pack(self, **kw):
        self.frame.pack(**kw)

    def set_state(self, state: str, text: Optional[str] = None):
        color = STATE_COLORS.get(state, FG_DIM)
        self._dot.itemconfig(self._dot_id, fill=color)
        self._label.config(text=text or state.capitalize())


class StatCard:
    """A small label/value stat block, e.g. 'API CALLS: 42'."""

    def __init__(self, parent, label: str):
        import tkinter as tk

        self.frame = tk.Frame(parent, bg=BG_PANEL)
        tk.Label(self.frame, text=label, bg=BG_PANEL, fg=FG_DIM, font=("Consolas", 8)).pack(
            anchor="w", padx=8, pady=(6, 0)
        )
        self._value = tk.Label(self.frame, text="-", bg=BG_PANEL, fg=FG, font=("Consolas", 14, "bold"))
        self._value.pack(anchor="w", padx=8, pady=(0, 6))

    def pack(self, **kw):
        self.frame.pack(**kw)

    def set_value(self, value):
        self._value.config(text=str(value))


class ScrollingLog:
    """Read-only auto-scrolling text log, capped at max_lines."""

    def __init__(self, parent, max_lines: int = 300, height: int = 14):
        import tkinter as tk

        self.max_lines = max_lines
        self.frame = tk.Frame(parent, bg=BG)
        self.text = tk.Text(
            self.frame,
            bg=BG,
            fg=FG,
            insertbackground=FG,
            font=("Consolas", 9),
            wrap="word",
            state="disabled",
            relief="flat",
            padx=8,
            pady=6,
            height=height,
        )
        scrollbar = tk.Scrollbar(self.frame, command=self.text.yview)
        self.text.configure(yscrollcommand=scrollbar.set)
        self.text.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        self.text.tag_config("dim", foreground=FG_DIM)
        self.text.tag_config("accent", foreground=ACCENT)
        self.text.tag_config("green", foreground=GREEN)
        self.text.tag_config("yellow", foreground=YELLOW)
        self.text.tag_config("red", foreground=RED)

    def pack(self, **kw):
        self.frame.pack(**kw)

    def clear(self):
        self.text.config(state="normal")
        self.text.delete("1.0", "end")
        self.text.config(state="disabled")

    def append(self, line: str, tag: Optional[str] = None):
        self.text.config(state="normal")
        self.text.insert("end", line + "\n", tag or "")
        line_count = int(self.text.index("end-1c").split(".")[0])
        if line_count > self.max_lines:
            self.text.delete("1.0", "2.0")
        self.text.see("end")
        self.text.config(state="disabled")


class Toast:
    """Self-dismissing colored banner for a single notification, packed at
    the top of any TkWindow. Used by dashboard (persistent panel isn't
    always visible) and available to overlay for error flashes. Build
    inside a TkWindow.build() callback; call show(level, title, message)
    from _on_event - it queues banners rather than fighting itself if a
    second notification arrives while the first is still showing.

    See ui/notifications.py for the level -> color mapping this mirrors
    (info/warning/error).
    """

    _COLORS = {"info": ACCENT, "warning": YELLOW, "error": RED}

    def __init__(self, parent, auto_hide_ms: int = 5000):
        import tkinter as tk

        self._tk = tk
        self._auto_hide_ms = auto_hide_ms
        self._queue: "list[tuple[str, str, str]]" = []
        self._hide_job = None
        self._parent = parent

        self.frame = tk.Frame(parent, bg=BG_PANEL)
        self._label = tk.Label(
            self.frame,
            text="",
            bg=BG_PANEL,
            fg=FG,
            font=("Consolas", 9, "bold"),
            anchor="w",
            justify="left",
            wraplength=360,
            padx=10,
            pady=6,
        )
        self._label.pack(fill="x")
        # Not packed into parent yet - only shown on demand, see show().

    def show(self, level: str, title: str, message: str = ""):
        text = f"{title} - {message}" if message else title
        self._queue.append((level, text, text))
        if self._hide_job is None:
            self._advance()

    def _advance(self):
        if not self._queue:
            self.frame.pack_forget()
            self._hide_job = None
            return
        level, text, _ = self._queue.pop(0)
        color = self._COLORS.get(level, ACCENT)
        self._label.config(text=text, fg=color)
        self.frame.pack(fill="x", side="top", before=self._first_sibling())
        self._hide_job = self.frame.after(self._auto_hide_ms, self._advance)

    def _first_sibling(self):
        siblings = self._parent.pack_slaves()
        return siblings[0] if siblings else None


class NotificationFeed:
    """A ScrollingLog pre-wired for ui.notifications.Notification payloads
    (as delivered via the 'notification' core.events topic) - used by
    dashboard's "NOTIFICATIONS" panel. Kept separate from ScrollingLog
    itself so ScrollingLog stays a generic text log."""

    _TAG = {"info": "accent", "warning": "yellow", "error": "red"}

    def __init__(self, parent, max_lines: int = 100, height: int = 6):
        self._log = ScrollingLog(parent, max_lines=max_lines, height=height)

    def pack(self, **kw):
        self._log.pack(**kw)

    def add(self, level: str, title: str, message: str = "", source: str = ""):
        prefix = {"info": "i", "warning": "!", "error": "\u2716"}.get(level, "i")
        line = f"[{prefix}] {title}"
        if message:
            line += f" - {message}"
        if source:
            line += f"  ({source})"
        self._log.append(line, self._TAG.get(level, "dim"))


class Widget:
    """Kept for import-compatibility with the original scaffolding
    (`ui.widgets.widgets.Widget().render(...)`). Prefer StatusPill,
    StatCard, or ScrollingLog directly for new code - this just documents
    that the widget catalogue now lives in this module."""

    def render(self, *args, **kwargs):
        raise NotImplementedError(
            "Widget.render() is a compatibility placeholder - use "
            "StatusPill, StatCard, or ScrollingLog from ui.widgets.widgets directly."
        )
