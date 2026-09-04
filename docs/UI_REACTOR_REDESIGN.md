# UI Redesign — Reactor HUD (ui/web_dashboard)

Replaced the old dashboard look with a more advanced "Reactor HUD" design:
templates/dashboard.html, static/css/dashboard.css, static/js/dashboard.js.

## What changed
- Central animated core (concentric rings, radar sweep, pulse glow) that reacts
  to assistant state: idle / listening / thinking / speaking / error each get
  their own core color + label + sweep speed.
- Arc gauges for CPU/RAM (SVG stroke-dashoffset, same r=52 math as before) with
  a color ramp (cyan/violet -> amber -> red as load increases).
- CPU/RAM history sparklines (canvas, unchanged MiniChart logic).
- Live conversation shown as chat bubbles (user = amber, right-aligned;
  Ultron = cyan, left-aligned) instead of a flat log.
- Activity panel lists tool calls as they happen.
- Ambient waveform bar in the footer brightens while listening/speaking.
- Connection pill (Live / Reconnecting) and uptime clock, same as before.

## Backend contract — unchanged
No changes to ui/web_dashboard/app.py. Still consumes:
- GET /api/stats (one-off snapshot)
- GET /api/uptime
- GET /api/stream (SSE: {type: stats|state|turn|tool})

So this drops in with zero backend changes — same event bus wiring from
core/assistant.py (wake_detected / thinking_start / tool_executed /
response_ready / speaking_start / speaking_end) drives it exactly as before.

## Known gaps / left as static
- The top ticker's "MODEL: GROQ ROUTER" and "SECURITY: SHIELD ACTIVE" badges
  are decorative placeholders — app.py doesn't currently expose which model
  answered or ULTRON_SHIELD's live status over the SSE stream. Wire these if
  you want them live (small addition to _stats_snapshot() or a new event type).
- No GPU temp / network I/O — ResourceMonitor.snapshot() doesn't collect
  those, so they were left out rather than faked.
