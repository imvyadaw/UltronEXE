# ui/web_ui/

Browser front end. Flask app in `app.py`; `templates/` (Jinja2) +
`static/` (css/js) follow Flask's default layout so nothing extra
needs configuring.

Run:

    python -m ui.web_ui.app

Defaults to `http://127.0.0.1:5000`. Override with
`ULTRON_WEB_UI_HOST`, `ULTRON_WEB_UI_PORT`, `ULTRON_WEB_UI_DEBUG` env
vars - see `config/default.yaml`'s `ui.web_ui` block for the target
values these should eventually be loaded from.

Talks to Ultron core through `ui/bridge.py`, not directly - if
`core.assistant` isn't importable yet, requests get an obvious stub
reply instead of failing, and the status dot in the header turns
amber. See `docs/architecture/phase7_ui_layer.md`.
