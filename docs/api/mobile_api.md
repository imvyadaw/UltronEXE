# Mobile API reference

Base URL (dev default): `http://127.0.0.1:5001/api/v1`

Auth: optional `X-API-Key` header, only enforced if
`ULTRON_MOBILE_API_KEY` is set on the server. See
`docs/architecture/phase7_ui_layer.md` for why this is a stopgap, not
production auth.

## POST /chat

Send a message, get Ultron's reply.

Request body:

```json
{
  "message": "what's on my calendar today",
  "session_id": "optional - omit to start a new session"
}
```

Response `200`:

```json
{
  "session_id": "generated-or-echoed-uuid",
  "reply": "...",
  "source": "core | stub",
  "timestamp": 1735689600.123
}
```

`source` is `"stub"` whenever `core.assistant` isn't wired in yet -
see `ui/bridge.py`. Treat it as a signal, not an error.

Response `400` if `message` is missing or empty:

```json
{ "error": "message is required" }
```

## GET /history/{session_id}

Returns the in-memory conversation history for a session (stub-only
today; core's real history store isn't wired in yet).

```json
{
  "session_id": "...",
  "messages": [
    { "role": "user", "text": "...", "ts": 1735689600.0 },
    { "role": "assistant", "text": "...", "ts": 1735689600.5 }
  ]
}
```

## GET /health

Passes through `monitoring.health_check.get_health_status()` if
wired, otherwise returns a stub status:

```json
{ "status": "unknown", "detail": "monitoring module not wired in yet", "source": "stub" }
```

## GET /status

Diagnostic - which core modules `ui/bridge.py` actually managed to
import:

```json
{ "assistant": false, "auth": false, "health_check": false }
```

## GET /notifications

Added in Phase 13. Recent items from `ui/notifications.py`'s shared
ring buffer - the same feed the desktop dashboard panel and web_ui
toasts read from, so a client failure (`core.assistant` throwing, an
upstream tool erroring) shows up here too. Optional query params:
`?since=<unix ts>` (only newer than this), `?level=info|warning|error`.

```json
{
  "notifications": [
    {
      "id": "uuid",
      "level": "error",
      "title": "Error",
      "message": "Ultron core failed to answer: ...",
      "source": "bridge.send_message",
      "timestamp": 1735689600.123
    }
  ]
}
```

## POST /notifications/register

Added in Phase 13. Registers a device's push token so a future
APNs/FCM push pipeline has somewhere to send to - **no push is
actually sent yet**, this only stores the token in memory (cleared on
server restart). See the module-level comment above
`_device_tokens` in `ui/mobile/api/routes.py`.

Request body:

```json
{ "device_id": "device-uuid", "push_token": "..." }
```

Response `200`:

```json
{ "registered": true, "device_id": "device-uuid" }
```

Response `400` if either field is missing:

```json
{ "error": "device_id and push_token are required" }
```
