# Mobile API - example requests

Assumes the server is running per `docs/guides/running_the_web_ui.md`:

```bash
python -m ui.mobile.api.routes
```

## Start a conversation

```bash
curl -X POST http://127.0.0.1:5001/api/v1/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "good morning"}'
```

## Continue it (reuse the session_id from the first response)

```bash
curl -X POST http://127.0.0.1:5001/api/v1/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "what did I just say?", "session_id": "PASTE_SESSION_ID"}'
```

## Read history

```bash
curl http://127.0.0.1:5001/api/v1/history/PASTE_SESSION_ID
```

## Health / status

```bash
curl http://127.0.0.1:5001/api/v1/health
curl http://127.0.0.1:5001/api/v1/status
```

## With API key auth enabled

If the server was started with `ULTRON_MOBILE_API_KEY` set:

```bash
export ULTRON_MOBILE_API_KEY=dev-key-123
ULTRON_MOBILE_API_KEY=$ULTRON_MOBILE_API_KEY python -m ui.mobile.api.routes &

curl -X POST http://127.0.0.1:5001/api/v1/chat \
  -H "Content-Type: application/json" \
  -H "X-API-Key: dev-key-123" \
  -d '{"message": "hello"}'
```

Omitting or mismatching `X-API-Key` in that case returns `401`:

```json
{ "error": "invalid or missing X-API-Key" }
```
