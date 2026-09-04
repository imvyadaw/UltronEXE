# Running the web UI

## Install

```bash
pip install -r ui/requirements-ui.txt
```

(Standalone for now - merge into the project's main requirements.txt
once one exists in this checkout.)

## Run

```bash
python -m ui.web_ui.app
```

Opens on `http://127.0.0.1:5000` by default. Override with env vars:

```bash
ULTRON_WEB_UI_HOST=0.0.0.0 ULTRON_WEB_UI_PORT=8080 ULTRON_WEB_UI_DEBUG=true \
  python -m ui.web_ui.app
```

## What you'll see

A single chat box. The dot next to "Ultron" in the header tells you
what you're actually talking to:

- **Green** - `core.assistant.Assistant` is importable and handling
  your messages for real.
- **Amber** - it isn't (expected on a fresh Phase 6 checkout), so
  you're talking to the in-memory stub in `ui/bridge.py`, which just
  echoes your message back. The UI itself still works end-to-end.

## Running the mobile API alongside it

The web UI and the mobile API are separate processes on separate
ports:

```bash
python -m ui.mobile.api.routes   # http://127.0.0.1:5001/api/v1
```

See `docs/api/mobile_api.md` for its endpoints and
`docs/examples/mobile_api_requests.md` for curl examples.
