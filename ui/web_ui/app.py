"""
ui.web_ui.app - browser front end for Ultron.

Run directly for local dev:

    python -m ui.web_ui.app

Config mirrors the pattern already used by Phase 5 modules (see
docs/architecture/phase6_config_storage.md): config/default.yaml
documents the target host/port under `ui.web_ui`, but no config
loader is wired in yet, so this module keeps its own hardcoded
defaults below, same as AuthManager.DEFAULT_SESSION_TTL_SECONDS does
today. Update both places if you change one.
"""

from __future__ import annotations

import os

from flask import Flask, jsonify, render_template, request

from ui import bridge
from ui import notifications as ui_notifications

# Mirrors config/default.yaml -> ui.web_ui.*
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 5000
DEFAULT_DEBUG = False


def create_app() -> Flask:
    app = Flask(
        __name__,
        static_folder="static",
        template_folder="templates",
    )

    @app.get("/")
    def index():
        return render_template("index.html")

    @app.post("/chat")
    def chat():
        payload = request.get_json(silent=True) or {}
        text = (payload.get("message") or "").strip()
        session_id = payload.get("session_id")

        if not text:
            return jsonify({"error": "message is required"}), 400

        result = bridge.send_message(text, session_id=session_id)
        return jsonify(
            {
                "session_id": result.session_id,
                "reply": result.reply,
                "source": result.source,
                "timestamp": result.timestamp,
            }
        )

    @app.get("/history/<session_id>")
    def history(session_id: str):
        return jsonify({"session_id": session_id, "messages": bridge.get_history(session_id)})

    @app.get("/health")
    def health():
        return jsonify(bridge.get_health())

    @app.get("/status")
    def status():
        return jsonify(bridge.core_wired())

    @app.get("/notifications")
    def notifications():
        # Phase 13. Polled (see static/js/chat.js) rather than pushed over
        # a websocket - this is a Flask dev-style app with no async
        # server yet, so a lightweight poll keeps the same "no new
        # dependency" approach as the rest of ui/web_ui.
        since = request.args.get("since", type=float)
        items = ui_notifications.get_recent(limit=50)
        if since:
            items = [n for n in items if n["timestamp"] > since]
        return jsonify({"notifications": items})

    return app


def main() -> None:
    app = create_app()
    host = os.environ.get("ULTRON_WEB_UI_HOST", DEFAULT_HOST)
    port = int(os.environ.get("ULTRON_WEB_UI_PORT", DEFAULT_PORT))
    debug = os.environ.get("ULTRON_WEB_UI_DEBUG", str(DEFAULT_DEBUG)).lower() == "true"
    app.run(host=host, port=port, debug=debug)


if __name__ == "__main__":
    main()
