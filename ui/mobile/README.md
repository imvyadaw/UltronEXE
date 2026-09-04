# ui/mobile/

Backend surface for the mobile client - `api/` is a versioned REST
API (`/api/v1/...`), not a mobile app itself. No mobile app source
lives in this repo.

Run standalone:

    python -m ui.mobile.api.routes

Defaults to `http://127.0.0.1:5001`. Override with
`ULTRON_MOBILE_API_HOST` / `ULTRON_MOBILE_API_PORT`.

Endpoints: see `docs/api/mobile_api.md`.

Auth is a dev-only stopgap right now (optional `X-API-Key` via
`ULTRON_MOBILE_API_KEY`) until `security.authentication.AuthManager`
(Phase 5) is wired in through `ui/bridge.py` - do not treat this as
production-ready auth.
