# Phase 7: UI layer

## ui/

Three independent surfaces, each runnable on its own:

- `ui/web_ui/` - a Flask app (`app.py`) serving `templates/` (Jinja2)
  and `static/` (css/js). A single-page chat view that POSTs to
  `/chat` and polls `/status` for a connection indicator.
- `ui/mobile/api/` - a versioned REST API (`/api/v1/...`) for a
  mobile client. No mobile app source lives here, just the backend
  it talks to.
- `ui/voice_ui/avatar/` - `AvatarController`, a state machine
  (`idle -> listening -> thinking -> speaking`, `error` reachable
  from anywhere) meant to be driven by the voice pipeline
  (`voice:` in `config/default.yaml`) and rendered by some future
  overlay/panel.

## ui/bridge.py

All three surfaces go through this one module to reach Ultron core -
`send_message`, `get_history`, `get_health`, `core_wired`. It tries to
import `core.assistant.Assistant`, `security.authentication.AuthManager`,
and `monitoring.health_check.get_health_status`; none of those are
expected to exist yet in a Phase 6 checkout, so on `ImportError` it
falls back to an in-memory stub assistant that echoes messages back.
This keeps `ui/` runnable and demoable without any core wiring, and
means nothing in `ui/` should need to change once core catches up -
only `ui/bridge.py`'s import block does.

The web UI's status dot and the mobile API's `/status` endpoint both
surface `core_wired()` so it's obvious at a glance whether you're
talking to the real assistant or the stub.

**Not yet wired in** (same situation Phase 6 described for its own
config): `config/default.yaml` now documents target values under a
new `ui:` section (`ui.web_ui`, `ui.mobile_api`, `ui.voice_ui`), but
`app.py` and `routes.py` still use their own hardcoded
`DEFAULT_HOST`/`DEFAULT_PORT` constants, same pattern as
`AuthManager.DEFAULT_SESSION_TTL_SECONDS`. Update both the yaml and
the constant if you change a default until a config loader exists.

Mobile API auth is a dev-only stopgap: an optional `X-API-Key` header
checked against `ULTRON_MOBILE_API_KEY`, skipped entirely if that env
var is unset. This is not `security.authentication.AuthManager` and
isn't meant to be - wiring real session auth through `ui/bridge.py`
is the natural next step, same as `_core_auth` being unused today.

## docs/

Added `api/`, `guides/`, and `examples/` alongside the existing
`architecture/`:

- `docs/api/mobile_api.md` - endpoint reference for `ui/mobile/api`.
- `docs/guides/running_the_web_ui.md` - how to start `ui/web_ui`
  locally.
- `docs/examples/mobile_api_requests.md` - copy-pasteable curl
  examples against the mobile API.

## testing/

`unit/`, `integration/`, `e2e/`, `mocks/` - see `testing/README.md`
for the full breakdown. Short version: `mocks/mock_core_assistant.py`
provides `MockCoreAssistant`/`BrokenCoreAssistant` so tests can
exercise `ui/bridge.py`'s "core is wired in" and "core raised, fall
back to stub" branches even though no real `core.assistant` exists in
this checkout yet - the same trick as `ui/bridge.py` itself. `unit/`
also tests `scripts/*.py` against a throwaway `scratch_project`
fixture rather than the real `storage/`/`config/`.

## scripts/

`setup.py`, `update.py`, `backup.py`, `maintenance.py` - see
`scripts/README.md`. Each exposes a `run(root=...)` function (used
directly by `testing/unit/test_scripts_*.py`) in addition to being
runnable as `python scripts/<name>.py`. `backup.py` is currently a
no-op in a fresh checkout, same as `storage/backups/` itself - there's
no module yet that writes a `.db` file for it to snapshot.

## Phase 13 addendum: notifications & error surfacing

Every UI surface already had some notion of an "error" state in its own
palette (dashboard's `StatusPill`, overlay/orb's `STATE_COLOR`/
`STATE_PALETTE`, tray's `STATE_COLORS`, voice_ui's `AvatarState.ERROR`)
but nothing in the codebase ever produced one - there was no shared
producer, and `voice_ui`'s `AvatarController` wasn't wired to
`core.events` at all, unlike every other surface.

Phase 13 adds `ui/notifications.py`: a small shared hub with
`notify(title, message, level)` / `report_error(message, source)`, a
bounded in-memory history (`get_recent()`), and re-emission onto
`core.events` as `"notification"` (always) and `"error"` (when
`level == "error"`). `ui/bridge.py` now calls `report_error()` when
`core.assistant.handle_message` raises, so there's a real trigger path
today, not just a documented convention.

Every surface subscribes to the new topic(s):

- `ui/dashboard` - a NOTIFICATIONS panel (`ui.widgets.widgets.NotificationFeed`),
  seeded from `get_recent()` on open so it isn't empty if something
  happened before the window was up.
- `ui/overlay` - shows the error pill for `ERROR_HIDE_MS` (8s) instead
  of the usual 4s.
- `ui/tray` - flashes the icon red and attempts an OS balloon via
  `pystray.Icon.notify()` (best-effort - not every backend supports it),
  auto-recovering to idle after 6s.
- `ui/orb` - finally exercises its long-unused `"error"` palette entry,
  auto-recovering to idle after 6s.
- `ui/voice_ui/avatar/bridge.py` (new) - wires `AvatarController` to
  `core.events` for the first time, mapping the existing
  thinking/speaking/wake/error topics onto LISTENING/THINKING/SPEAKING/
  IDLE/ERROR per the mapping `avatar/states.py` already documented.
- `ui/web_ui` - `GET /notifications` (polled every 4s by `chat.js`) with
  a toast stack in `base.html`.
- `ui/mobile/api` - `GET /notifications` (same feed) plus
  `POST /notifications/register` for a future push pipeline; currently
  stores device tokens in memory only and does not send pushes yet.
