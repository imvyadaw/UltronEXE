"""
ui.mobile.api.routes - REST API consumed by the mobile client.

Versioned under /api/v1 so the web_ui and the mobile client can evolve
independently. Runnable standalone:

    python -m ui.mobile.api.routes

or mounted into another Flask app via `blueprint`.

Auth: security.authentication.AuthManager (Phase 5) is not wired in
here yet - see ui/bridge.py. In the meantime, requests must send
ULTRON_MOBILE_API_KEY's value as the `X-API-Key` header. This is a
stopgap for local/dev use, NOT a replacement for real session auth -
don't rely on it in production.

ULTRON_MOBILE_API_AUTH_REQUIRED defaults to true (fail closed): if
ULTRON_MOBILE_API_KEY isn't configured, every request gets a 503
"not configured" response rather than an open API. Set
ULTRON_MOBILE_API_AUTH_REQUIRED=false explicitly to disable the gate
entirely (e.g. for local testing) - only then is the API open.
"""

from __future__ import annotations

import hmac
import os

from flask import Blueprint, Flask, jsonify, request

from ui import bridge
from ui import notifications as ui_notifications
from ui.mobile.api.schemas import ChatRequest, ChatResponse, ErrorResponse, StatusResponse

# Mirrors config/default.yaml -> ui.mobile_api.*
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 5001
API_PREFIX = "/api/v1"

blueprint = Blueprint("mobile_api", __name__, url_prefix=API_PREFIX)

# Hard upper bound for JSON request bodies. Keep this conservative because
# mobile requests are small and oversized payloads should be rejected early.
MAX_REQUEST_BYTES = 256 * 1024


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _api_key_required():
    if not _env_bool("ULTRON_MOBILE_API_AUTH_REQUIRED", True):
        return None

    expected = (os.environ.get("ULTRON_MOBILE_API_KEY") or "").strip()
    if not expected:
        return jsonify(ErrorResponse("mobile API authentication is not configured").to_json()), 503

    provided = request.headers.get("X-API-Key", "")
    if not provided or not hmac.compare_digest(provided, expected):
        return jsonify(ErrorResponse("invalid or missing X-API-Key").to_json()), 401
    return None


@blueprint.before_request
def _check_request():
    if request.content_length is not None and request.content_length > MAX_REQUEST_BYTES:
        return jsonify(ErrorResponse("request body too large").to_json()), 413
    return _api_key_required()


@blueprint.post("/chat")
def chat():
    payload = request.get_json(silent=True) or {}
    try:
        chat_request = ChatRequest.from_json(payload)
    except ValueError as exc:
        return jsonify(ErrorResponse(str(exc)).to_json()), 400

    result = bridge.send_message(chat_request.message, session_id=chat_request.session_id)
    response = ChatResponse(
        session_id=result.session_id,
        reply=result.reply,
        source=result.source,
        timestamp=result.timestamp,
    )
    return jsonify(response.to_json())


@blueprint.get("/history/<session_id>")
def history(session_id: str):
    return jsonify({"session_id": session_id, "messages": bridge.get_history(session_id)})


@blueprint.get("/notifications")
def notifications():
    """Phase 13. Same ui.notifications ring buffer the desktop dashboard
    and web_ui poll - lets the mobile client show a badge/list of recent
    errors and other notices without needing its own websocket/SSE
    client yet. `?since=<unix ts>` filters to anything newer."""
    since = request.args.get("since", type=float)
    level = request.args.get("level")
    items = ui_notifications.get_recent(limit=50, level=level)
    if since:
        items = [n for n in items if n["timestamp"] > since]
    return jsonify({"notifications": items})


# In-memory only, cleared on restart - a real push-notification pipeline
# (APNs/FCM) needs a persistent store and a background sender, neither of
# which exists yet. This is the same "documents the target interface,
# stubbed until the real thing is wired in" pattern as ui/bridge.py's
# fallback to _StubAssistant: registering a token here doesn't yet cause
# any push to actually be sent, but the client-facing contract is real.
_device_tokens: dict[str, str] = {}


@blueprint.post("/notifications/register")
def register_device():
    """Body: {"device_id": "...", "push_token": "..."}. Stopgap until a
    real push pipeline exists - see module-level note above."""
    payload = request.get_json(silent=True) or {}
    device_id = (payload.get("device_id") or "").strip()
    push_token = (payload.get("push_token") or "").strip()
    if not device_id or not push_token:
        return jsonify(ErrorResponse("device_id and push_token are required").to_json()), 400
    _device_tokens[device_id] = push_token
    return jsonify({"registered": True, "device_id": device_id})


@blueprint.get("/health")
def health():
    return jsonify(bridge.get_health())


@blueprint.get("/status")
def status():
    wired = bridge.core_wired()
    return jsonify(StatusResponse(**wired).to_json())


def create_app() -> Flask:
    app = Flask(__name__)
    app.register_blueprint(blueprint)
    return app


def main() -> None:
    app = create_app()
    host = os.environ.get("ULTRON_MOBILE_API_HOST", DEFAULT_HOST)
    port = int(os.environ.get("ULTRON_MOBILE_API_PORT", DEFAULT_PORT))
    app.run(host=host, port=port)


if __name__ == "__main__":
    main()
