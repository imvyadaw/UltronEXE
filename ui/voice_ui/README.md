# ui/voice_ui/

Visual companion for the voice pipeline (`voice:` section of
config/default.yaml - wake word, STT/TTS mode).

`avatar/states.py` defines `AvatarController`, a small state machine
(`idle -> listening -> thinking -> speaking -> idle`, with `error`
reachable from anywhere) that any renderer can subscribe to via
`on_change(callback)`.

As of Phase 13, `avatar/bridge.py` wires that controller to
`core.events` the same way dashboard/overlay/tray/orb already do -
call `ui.voice_ui.avatar.get_avatar_controller()` to get the
process-wide, already-wired singleton. It maps the existing
thinking_start/speaking_start/speaking_end/response_ready/wake_detected/
error topics onto LISTENING/THINKING/SPEAKING/IDLE/ERROR, and
auto-recovers ERROR back to IDLE after a few seconds (there's no
"pipeline exception cleared" event to listen for). This is still not
driven by a *real* voice pipeline - `core.events` itself isn't emitted
by a `voice.*` module yet, only by main.py's text/typed-voice REPL
paths - but the controller no longer sits completely disconnected.

`avatar/assets/` holds the per-state visuals once there's a renderer
to consume them; empty for now.

`avatar/assets/` holds the per-state visuals once there's a renderer
to consume them; empty for now.
