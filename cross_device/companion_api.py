"""
companion_api.py
====================
A small local HTTP surface for the companion mobile/desktop app to
hit for the handful of things that don't fit naturally over the
WebSocket stream: starting a pairing flow, checking host status, and
listing what a device is currently granted. This is deliberately
thin - actual live traffic (notifications, clipboard, remote
commands) all flows through `websocket_server.py`.

Binds to localhost by default. Standard library only (`http.server`)
- no Flask/FastAPI dependency for something this small.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Optional
from urllib.parse import urlparse

from .device_manager import DeviceManager, DeviceType
from .remote_controller import RemoteController

logger = logging.getLogger("ultron.companion_api")


class CompanionAPI:
    """Wraps a stdlib HTTP server exposing a few JSON endpoints:

    GET  /status                      -> host status, uptime, device count
    POST /pair/start   {device_type}  -> {"code": "..."}
    POST /pair/confirm {code, name}   -> device_id + token, or 401
    GET  /devices/<id>/commands       -> commands granted to that device
    """

    def __init__(
        self,
        device_manager: DeviceManager,
        remote_controller: Optional[RemoteController] = None,
        host: str = "0.0.0.0",
        port: int = 8766,
        host_name: str = "ULTRON",
    ):
        self.device_manager = device_manager
        self.remote_controller = remote_controller
        self.host = host
        self.port = port
        self.host_name = host_name
        self._start_time = datetime.now()
        self._server: Optional[ThreadingHTTPServer] = None

    def start(self) -> None:
        handler_cls = self._build_handler()
        self._server = ThreadingHTTPServer((self.host, self.port), handler_cls)
        logger.info("CompanionAPI listening on http://%s:%s", self.host, self.port)
        self._server.serve_forever()

    def start_in_thread(self) -> None:
        import threading

        threading.Thread(target=self.start, daemon=True).start()

    def stop(self) -> None:
        if self._server:
            self._server.shutdown()

    # ------------------------------------------------------------------ handler
    def _build_handler(self):
        api = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, fmt, *args):
                logger.info("%s - %s", self.address_string(), fmt % args)

            def _json(self, status: int, payload: dict) -> None:
                body = json.dumps(payload).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def _read_json_body(self) -> dict:
                length = int(self.headers.get("Content-Length", 0))
                if length == 0:
                    return {}
                raw = self.rfile.read(length)
                try:
                    return json.loads(raw)
                except json.JSONDecodeError:
                    return {}

            def do_GET(self):
                parsed = urlparse(self.path)
                if parsed.path == "/status":
                    uptime = (datetime.now() - api._start_time).total_seconds()
                    self._json(
                        200,
                        {
                            "host_name": api.host_name,
                            "uptime_seconds": uptime,
                            "device_count": len(api.device_manager.list_devices()),
                        },
                    )
                elif parsed.path.startswith("/devices/") and parsed.path.endswith("/commands"):
                    device_id = parsed.path.split("/")[2]
                    granted = api.remote_controller.granted_commands(device_id) if api.remote_controller else []
                    self._json(200, {"device_id": device_id, "granted_commands": granted})
                else:
                    self._json(404, {"error": "not found"})

            def do_POST(self):
                parsed = urlparse(self.path)
                body = self._read_json_body()

                if parsed.path == "/pair/start":
                    try:
                        device_type = DeviceType(body.get("device_type", "other"))
                    except ValueError:
                        device_type = DeviceType.OTHER
                    code = api.device_manager.start_pairing(device_type)
                    self._json(200, {"code": code, "expires_in_seconds": 300})

                elif parsed.path == "/pair/confirm":
                    code = body.get("code", "")
                    name = body.get("name", "Unnamed device")
                    device = api.device_manager.pair(code, name)
                    if device is None:
                        self._json(401, {"error": "invalid or expired code"})
                    else:
                        self._json(
                            200,
                            {
                                "device_id": device.device_id,
                                "token": device.token,
                                "device_type": device.device_type.value,
                            },
                        )
                else:
                    self._json(404, {"error": "not found"})

        return Handler


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    dm = DeviceManager(store_path="ultron_data/cross_device/_demo_devices.json")
    rc = RemoteController(log_path="ultron_data/cross_device/_demo_remote_log.json")
    api = CompanionAPI(dm, rc)
    print(f"Demo API on http://{api.host}:{api.port} - try: curl http://127.0.0.1:8766/status")
    try:
        api.start()
    except KeyboardInterrupt:
        from core.error_trace import log_swallowed as _lsw

        _lsw("cross_device.companion_api.<module>")
