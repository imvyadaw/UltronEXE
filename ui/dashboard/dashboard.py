"""
Dashboard
=========
A live status window for Ultron: current state, a real-time activity log
(thinking/tool calls/replies/speaking), API usage stats, and recently
saved conversation sessions. Runs on its own Tk thread (see
ui.widgets.widgets.TkWindow) so it never touches main.py's blocking
input() loop. Subscribes to core.events for live updates.

Safe to never open - nothing else depends on it. Open it either from the
tray menu ("Open Dashboard") or directly:

    from ui.dashboard.dashboard import open_dashboard
    open_dashboard()
"""

import time
from typing import Optional

from core.events import get_event_bus
from core.logger import get_logger
from ui.widgets.widgets import (
    TkWindow,
    StatusPill,
    StatCard,
    ScrollingLog,
    NotificationFeed,
    Toast,
    BG,
    BG_PANEL,
    FG,
    FG_DIM,
)
from ui.notifications import get_recent as get_recent_notifications

logger = get_logger("ultron.ui.dashboard")

_window: Optional[TkWindow] = None
_start_time = time.time()
_wired = False


def _build(win: TkWindow, root):
    import tkinter as tk

    header = tk.Frame(root, bg=BG_PANEL)
    header.pack(fill="x")
    tk.Label(header, text="ULTRON", bg=BG_PANEL, fg=FG, font=("Consolas", 16, "bold")).pack(
        side="left", padx=10, pady=8
    )
    win.pill = StatusPill(header)
    win.pill.pack(side="right", padx=8)

    win.toast = Toast(root)

    stats = tk.Frame(root, bg=BG)
    stats.pack(fill="x", padx=8, pady=8)
    win.calls_card = StatCard(stats, "API CALLS")
    win.calls_card.pack(side="left", expand=True, fill="x", padx=4)
    win.tokens_card = StatCard(stats, "TOKENS USED")
    win.tokens_card.pack(side="left", expand=True, fill="x", padx=4)
    win.uptime_card = StatCard(stats, "UPTIME")
    win.uptime_card.pack(side="left", expand=True, fill="x", padx=4)

    tk.Label(root, text="LIVE ACTIVITY", bg=BG, fg=FG_DIM, font=("Consolas", 8, "bold")).pack(anchor="w", padx=10)
    win.log = ScrollingLog(root, height=16)
    win.log.pack(fill="both", expand=True, padx=8, pady=(0, 8))

    tk.Label(root, text="RECENT SAVED SESSIONS", bg=BG, fg=FG_DIM, font=("Consolas", 8, "bold")).pack(
        anchor="w", padx=10
    )
    win.sessions = ScrollingLog(root, max_lines=50, height=6)
    win.sessions.pack(fill="x", padx=8, pady=(0, 8))

    tk.Label(root, text="NOTIFICATIONS", bg=BG, fg=FG_DIM, font=("Consolas", 8, "bold")).pack(anchor="w", padx=10)
    win.notifications = NotificationFeed(root, max_lines=100, height=6)
    win.notifications.pack(fill="x", padx=8, pady=(0, 8))
    # Seed with whatever was raised before the dashboard was opened (see
    # ui/notifications.py's ring buffer) so nothing's missed just because
    # the window wasn't up yet.
    for n in get_recent_notifications(limit=20):
        win.notifications.add(n["level"], n["title"], n.get("message", ""), n.get("source", ""))

    _refresh_stats(win)
    win.root.after(1000, lambda: _tick_uptime(win))
    win.root.after(5000, lambda: _refresh_loop(win))


def _refresh_stats(win: TkWindow):
    try:
        from storage.cache.usage_tracker import UsageTracker

        summary = UsageTracker().get_usage_summary()
        win.calls_card.set_value(summary.get("total_calls", 0))
        win.tokens_card.set_value(summary.get("total_tokens", 0))
    except Exception as e:
        logger.error(f"Dashboard usage refresh failed: {e}")

    try:
        from memory.history.history import ConversationHistoryStore

        result = ConversationHistoryStore().list_sessions(limit=8)
        win.sessions.clear()
        for s in result.get("sessions", []):
            preview = (s.get("preview") or "").replace("\n", " ")[:60]
            win.sessions.append(f"#{s['session_id']}  ({s['message_count']} msgs)  {preview}", "dim")
    except Exception as e:
        logger.error(f"Dashboard sessions refresh failed: {e}")


def _tick_uptime(win: TkWindow):
    elapsed = int(time.time() - _start_time)
    h, rem = divmod(elapsed, 3600)
    m, s = divmod(rem, 60)
    win.uptime_card.set_value(f"{h:02d}:{m:02d}:{s:02d}")
    win.root.after(1000, lambda: _tick_uptime(win))


def _refresh_loop(win: TkWindow):
    _refresh_stats(win)
    win.root.after(5000, lambda: _refresh_loop(win))


def _on_event(win: TkWindow, event: str, data: dict):
    if event == "state":
        win.pill.set_state(data.get("state", "idle"), data.get("text"))
    elif event == "log":
        win.log.append(data.get("line", ""), data.get("tag"))
    elif event == "notification":
        win.notifications.add(
            data.get("level", "info"),
            data.get("title", ""),
            data.get("message", ""),
            data.get("source", ""),
        )
        if data.get("level") in ("warning", "error"):
            # The persistent panel is easy to miss if the window isn't in
            # focus - a transient Toast at the top makes warnings/errors
            # hard to miss without needing the OS-level tray balloon.
            win.toast.show(data.get("level", "info"), data.get("title", ""), data.get("message", ""))
        if data.get("level") == "error":
            win.pill.set_state("error", data.get("title"))


def _wire_events(win: TkWindow):
    global _wired
    if _wired:
        return
    _wired = True
    bus = get_event_bus()

    def state(name, text=None):
        win.post("state", state=name, text=text)

    def log(line, tag=None):
        win.post("log", line=line, tag=tag)

    bus.subscribe("thinking_start", lambda **kw: (state("thinking"), log(f"> {kw.get('text', '')}", "accent")))
    bus.subscribe("tool_executed", lambda **kw: log(f"  [tool] {kw.get('name')}({kw.get('args_str', '')})", "accent"))
    bus.subscribe("response_ready", lambda **kw: (state("idle"), log(f"ULTRON: {kw.get('text', '')}", None)))
    bus.subscribe("speaking_start", lambda **kw: state("speaking"))
    bus.subscribe("speaking_end", lambda **kw: state("idle"))
    bus.subscribe("wake_detected", lambda **kw: state("listening"))
    bus.subscribe("notification", lambda **kw: win.post("notification", **kw))


def open_dashboard() -> TkWindow:
    """Open the dashboard window - creates it on first call, no-ops if it's
    already open. Safe to call from any thread (e.g. the tray icon's own
    thread, which is where the 'Open Dashboard' menu item calls this)."""
    global _window
    if _window is None or not _window.is_alive():
        _window = TkWindow("ULTRON Dashboard", build=_build, on_event=_on_event, size="480x600")
        _window.start()
        _window.wait_ready()
    _wire_events(_window)
    return _window


class Dashboard:
    """Kept for import-compatibility with the original scaffolding
    (`ui.dashboard.dashboard.Dashboard().launch()`)."""

    def launch(self, *args, **kwargs):
        return open_dashboard()
