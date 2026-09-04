"""
ui.web_dashboard - real-time browser dashboard for Ultron.

Shows, live, updating without a page refresh:
  - CPU / RAM / disk / battery usage (polled from psutil every second)
  - Ultron's current state (idle / listening / thinking / speaking)
  - A live conversation feed (every command you give + every reply Ultron
    gives), plus tool calls as they happen

Data flow:
  - System stats: a background thread snapshots monitoring/resource_monitor.py
    (ResourceMonitor) once a second and pushes onto every connected
    client's queue.
  - Conversation/activity events: this module subscribes to the SAME
    core.events event bus that core/assistant.py already emits on for
    every turn (thinking_start / tool_executed / response_ready /
    speaking_start / speaking_end / wake_detected) - nothing in
    core/assistant.py needed to change for this to work, it was already
    wired for exactly this ("ui/dashboard ... subscribe() to it", see
    core/events.py's own docstring).
  - Both are delivered to the browser over one Server-Sent-Events (SSE)
    stream per connected client (GET /api/stream) - no extra dependency
    (websockets/flask-sock) needed, SSE is plain HTTP and Flask's dev
    server handles it fine for a single local user.

Run directly:
    python -m ui.web_dashboard.app
or import open_dashboard()/start_dashboard() from elsewhere (see
ui/tray/tray.py, which now opens this instead of the old Tk dashboard).
"""

from __future__ import annotations

import json
import queue
import threading
import time
import webbrowser
from typing import Dict, Optional

from flask import Flask, Response, jsonify, render_template, request

from core.events import get_event_bus
from core.logger import get_logger

logger = get_logger("ultron.ui.web_dashboard")

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 5678
STATS_INTERVAL_SECONDS = 1.0

_start_time = time.time()

# Every connected browser tab gets its own Queue; the stats thread and the
# event-bus subscribers below fan out to all of them. A dead/slow client
# just stops being read from - it doesn't block anyone else (bounded queue
# + drop-oldest, see _broadcast).
_clients: "list[queue.Queue]" = []
_clients_lock = threading.Lock()

_wired = False
_wire_lock = threading.Lock()

# The live Assistant instance (core/assistant.py), set by start_dashboard()
# when Ultron itself opens the dashboard (runtime.open_dashboard() /
# "dashboard on" / --dashboard). Lets the browser's command box call
# handle_command() on the SAME instance already holding conversation
# history/context - not a second, disconnected one. Stays None if the
# dashboard is ever launched standalone (`python -m ui.web_dashboard.app`)
# without a running assistant; /api/command reports that clearly instead
# of building an unrelated assistant behind the user's back.
_assistant = None


def _broadcast(payload: Dict) -> None:
    data = json.dumps(payload)
    with _clients_lock:
        dead = []
        for q in _clients:
            try:
                q.put_nowait(data)
            except queue.Full:
                # Slow client - drop the oldest item to make room rather
                # than blocking the emitter (which would stall the whole
                # assistant loop, since this runs on the same thread that
                # calls bus.emit()).
                try:
                    q.get_nowait()
                    q.put_nowait(data)
                except Exception:
                    dead.append(q)
        for q in dead:
            _clients.remove(q)


def _stats_snapshot() -> Dict:
    try:
        snap = _stats_snapshot._monitor.snapshot()
    except Exception as e:
        return {"type": "stats", "error": str(e)}
    snap["type"] = "stats"
    try:
        import psutil

        battery = psutil.sensors_battery()
        if battery is not None:
            snap["battery_percent"] = battery.percent
            snap["battery_plugged"] = battery.power_plugged
    except Exception:
        from core.error_trace import log_swallowed as _lsw

        _lsw("ui.web_dashboard.app._stats_snapshot")
    try:
        from core.control_mode import safe_control_enabled, unsafe_control_enabled

        snap["auto_mode_safe"] = safe_control_enabled()
        snap["auto_mode_unsafe"] = unsafe_control_enabled()
    except Exception:
        from core.error_trace import log_swallowed as _lsw

        _lsw("ui.web_dashboard.app._stats_snapshot.control_mode")
    return snap


def _init_monitor():
    from monitoring.resource_monitor import ResourceMonitor

    _stats_snapshot._monitor = ResourceMonitor()


def _stats_loop():
    while True:
        try:
            _broadcast(_stats_snapshot())
        except Exception:
            logger.exception("web_dashboard stats loop failed")
        time.sleep(STATS_INTERVAL_SECONDS)


def _wire_events():
    """Subscribe once to core.events - same bus core/assistant.py and the
    old Tk dashboard use, so every command/reply/tool-call this dashboard
    shows is coming straight from the real assistant loop, live."""
    global _wired
    with _wire_lock:
        if _wired:
            return
        _wired = True

    bus = get_event_bus()

    def _on_wake(**kw):
        _broadcast({"type": "state", "state": "listening"})

    def _on_thinking(**kw):
        _broadcast({"type": "state", "state": "thinking"})
        _broadcast({"type": "turn", "role": "user", "text": kw.get("text", "")})

    def _on_tool(**kw):
        _broadcast({"type": "tool", "name": kw.get("name", ""), "args": kw.get("args_str", "")})

    def _on_response(**kw):
        _broadcast({"type": "state", "state": "idle"})
        _broadcast({"type": "turn", "role": "ultron", "text": kw.get("text", "")})

    def _on_speaking_start(**kw):
        _broadcast({"type": "state", "state": "speaking"})

    def _on_speaking_end(**kw):
        _broadcast({"type": "state", "state": "idle"})

    def _on_image(**kw):
        # From ai/image_display_tools.py's show_image tool - always a
        # real, verified photo (Wikipedia/Wikimedia), never generated.
        _broadcast(
            {
                "type": "image",
                "url": kw.get("url", ""),
                "title": kw.get("title", ""),
                "description": kw.get("description", ""),
                "source_url": kw.get("source_url", ""),
            }
        )

    bus.subscribe("wake_detected", _on_wake)
    bus.subscribe("thinking_start", _on_thinking)
    bus.subscribe("tool_executed", _on_tool)
    bus.subscribe("response_ready", _on_response)
    bus.subscribe("speaking_start", _on_speaking_start)
    bus.subscribe("speaking_end", _on_speaking_end)
    bus.subscribe("image_ready", _on_image)


def create_app(assistant=None) -> Flask:
    app = Flask(__name__, static_folder="static", template_folder="templates")
    global _assistant
    if assistant is not None:
        _assistant = assistant
    _init_monitor()
    _wire_events()

    stats_thread = threading.Thread(target=_stats_loop, daemon=True, name="ultron-dashboard-stats")
    stats_thread.start()

    @app.get("/")
    def index():
        return render_template("dashboard.html")

    @app.get("/api/stats")
    def api_stats():
        """One-off snapshot - used for the very first paint before the SSE
        stream has delivered anything yet, so the page never shows an
        empty/zeroed dashboard while waiting for the first tick."""
        return jsonify(_stats_snapshot())

    @app.get("/api/uptime")
    def api_uptime():
        return jsonify({"uptime_seconds": time.time() - _start_time})

    @app.post("/api/command")
    def api_command():
        """Lets the dashboard's command box type a command the exact same
        way the tray/wake-word/terminal do - runs it through the live
        Assistant's own handle_command(), the same entry point run_text()
        and run_listen() already use, so it gets full tool-routing,
        context, and history, not a stripped-down web-only path.

        handle_command() is synchronous and can call an LLM (seconds, not
        milliseconds), so it runs on a background thread - this request
        returns immediately with 202 (queued), and the actual reply shows
        up in the conversation feed the normal way, over the existing SSE
        stream (handle_command already emits thinking_start/response_ready
        on core.events, which this module already subscribes to - see
        _wire_events() above - so no separate response path is needed
        here)."""
        if _assistant is None:
            return (
                jsonify(
                    {
                        "error": "No running Ultron assistant is attached to this dashboard "
                        "(it was likely started standalone, without the app). "
                        "Start Ultron normally and open the dashboard from there.",
                    }
                ),
                503,
            )

        data = request.get_json(silent=True) or {}
        text = (data.get("text") or "").strip()
        if not text:
            return jsonify({"error": "Empty command."}), 400

        def _run():
            try:
                _assistant.handle_command(text)
            except Exception:
                logger.exception("web_dashboard: handle_command failed for typed command")
                _broadcast(
                    {
                        "type": "turn",
                        "role": "ultron",
                        "text": "Sorry Sir, that command hit an internal error - check the logs.",
                    }
                )
                _broadcast({"type": "state", "state": "idle"})

        threading.Thread(target=_run, daemon=True, name="ultron-dashboard-command").start()
        return jsonify({"queued": True}), 202

    @app.get("/api/stream")
    def api_stream():
        client_q: "queue.Queue[str]" = queue.Queue(maxsize=200)
        with _clients_lock:
            _clients.append(client_q)

        def gen():
            try:
                # Prime the connection immediately so the browser's
                # EventSource fires onopen right away instead of waiting
                # for the first real event.
                yield "event: ping\ndata: {}\n\n"
                while True:
                    try:
                        data = client_q.get(timeout=15)
                        yield f"data: {data}\n\n"
                    except queue.Empty:
                        # Keep-alive comment line - stops proxies/browsers
                        # from timing out an idle SSE connection.
                        yield ": keep-alive\n\n"
            except GeneratorExit:
                from core.error_trace import log_swallowed as _lsw

                _lsw("ui.web_dashboard.app.gen")
            finally:
                with _clients_lock:
                    if client_q in _clients:
                        _clients.remove(client_q)

        return Response(
            gen(),
            mimetype="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
            },
        )

    return app


_server_thread: Optional[threading.Thread] = None
_server_lock = threading.Lock()


def start_dashboard(
    host: str = DEFAULT_HOST, port: int = DEFAULT_PORT, open_browser: bool = True, assistant=None
) -> None:
    """Start the dashboard's Flask server on a background daemon thread
    (never blocks the caller - safe to call from main.py's --ui path or
    the tray icon, same contract as ui/orb.open_orb). Safe to call more
    than once; only the first call actually starts a server.

    `assistant`: the live core.assistant.Assistant instance (passed by
    Assistant.open_dashboard()) that the dashboard's command box sends
    typed commands to. None if launched standalone."""
    global _server_thread, _assistant
    with _server_lock:
        if assistant is not None:
            _assistant = assistant
        if _server_thread is not None and _server_thread.is_alive():
            if open_browser:
                webbrowser.open(f"http://{host}:{port}/")
            return

        app = create_app(assistant=assistant)

        def _run():
            try:
                app.run(host=host, port=port, debug=False, use_reloader=False, threaded=True)
            except Exception:
                logger.exception("web_dashboard server failed to start")

        _server_thread = threading.Thread(target=_run, daemon=True, name="ultron-dashboard-server")
        _server_thread.start()

    if open_browser:
        # Give the server a moment to bind before the browser requests it.
        threading.Timer(0.6, lambda: webbrowser.open(f"http://{host}:{port}/")).start()


def open_dashboard() -> None:
    """Back-compat entry point matching the old ui.dashboard.dashboard.open_dashboard()
    signature used by ui/tray/tray.py - starts the server (if not already
    running) and opens it in the default browser."""
    start_dashboard()


def main() -> None:
    start_dashboard(open_browser=True)
    # Keep the main thread alive when run standalone (python -m ...) -
    # the actual server runs on the daemon thread started above.
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        from core.error_trace import log_swallowed as _lsw

        _lsw("ui.web_dashboard.app.main")


if __name__ == "__main__":
    main()
