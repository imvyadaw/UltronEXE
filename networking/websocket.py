"""
WebSocket client
=================
Thin wrapper around `websocket-client` for the handful of Ultron features
that need a persistent connection instead of request/response (e.g. a
future live-transcription bridge, or a real-time price/status feed) -
networking/http_client.py covers everything else.

Runs the connection in a background thread so callers aren't blocked;
messages are handed to a callback rather than requiring the caller to
poll. Optional dependency, same pattern as ai/embeddings.py -
send()/close() raise a clear error if `websocket-client` isn't installed
rather than failing at import time.
"""

import threading
from typing import Callable, Dict, Optional

try:
    import websocket as _ws_lib

    HAS_WEBSOCKET_CLIENT = True
except ImportError:
    HAS_WEBSOCKET_CLIENT = False


class WebSocketClient:
    """Background-threaded websocket connection with callback-based message handling."""

    def __init__(
        self,
        url: str,
        on_message: Optional[Callable[[str], None]] = None,
        on_error: Optional[Callable[[Exception], None]] = None,
        on_close: Optional[Callable[[], None]] = None,
    ):
        self.url = url
        self._on_message = on_message
        self._on_error = on_error
        self._on_close = on_close
        self._app: Optional["_ws_lib.WebSocketApp"] = None
        self._thread: Optional[threading.Thread] = None
        self._connected = threading.Event()
        self._connect_error: Optional[str] = None

    def connect(self, timeout: int = 10) -> Dict:
        """Open the connection in a background thread and block up to
        `timeout` seconds for it to actually establish before returning."""
        if not HAS_WEBSOCKET_CLIENT:
            return {
                "error": "The 'websocket-client' package is required. Install it with: pip install websocket-client"
            }

        try:

            def _on_open(app):
                self._connected.set()

            def _on_message(app, message):
                if self._on_message:
                    self._on_message(message)

            def _on_error(app, error):
                self._connect_error = str(error)
                if self._on_error:
                    self._on_error(error)

            def _on_close(app, close_status_code, close_msg):
                self._connected.clear()
                if self._on_close:
                    self._on_close()

            self._app = _ws_lib.WebSocketApp(
                self.url,
                on_open=_on_open,
                on_message=_on_message,
                on_error=_on_error,
                on_close=_on_close,
            )
            self._thread = threading.Thread(target=self._app.run_forever, daemon=True)
            self._thread.start()

            established = self._connected.wait(timeout=timeout)
            if not established:
                return {"error": self._connect_error or f"Connection to {self.url} timed out after {timeout}s"}

            return {"success": True, "url": self.url}
        except Exception as e:
            return {"error": str(e)}

    def send(self, message: str) -> Dict:
        if not self._app or not self._connected.is_set():
            return {"error": "Not connected - call connect() first"}
        try:
            self._app.send(message)
            return {"success": True}
        except Exception as e:
            return {"error": str(e)}

    def is_connected(self) -> bool:
        return self._connected.is_set()

    def close(self) -> Dict:
        try:
            if self._app:
                self._app.close()
            self._connected.clear()
            return {"success": True}
        except Exception as e:
            return {"error": str(e)}
