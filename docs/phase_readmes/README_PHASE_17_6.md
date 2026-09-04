# PHASE 17.6 — AUTOMATION — build notes

Everything in your original tree got built except one file, and a
few others were scoped differently than the filename alone might
suggest. Explaining the "why" here once instead of repeating it in
every docstring.

## Not built: `captcha_solver.py`

I didn't build this one. CAPTCHAs exist specifically to tell humans
and bots apart, so code whose purpose is defeating that check is
something I stay away from regardless of the reason it's wanted for —
that's true even inside a personal assistant project. `web_agent_core.py`
has a `looks_like_challenge_page()` helper instead: when it detects a
captcha/challenge page, the right move is to pause and let you (the
human) clear it, then hand control back to the agent.

## Built, but scoped narrower than the filename might imply

- **`global_hook_manager.py`** — registers specific hotkeys/gestures
  you name (e.g. `ctrl+shift+j`) and fires a callback. It does not
  log every keystroke — a "record everything typed" module is
  functionally a keylogger no matter what folder it lives in.

- **`clipboard_intelligence.py`** — classifies clipboard content
  (URL/email/phone/code) for in-the-moment suggestions. History is
  in-memory, capped, and never written to disk or sent anywhere by
  this module. Clipboard content routinely includes passwords and
  OTPs, so silent persistent logging isn't a default I wanted to
  ship even for your own machine.

- **`network_monitor.py`** — bandwidth, interface status, and active
  connection metadata (like Task Manager's network tab). No packet
  payload capture/sniffing.

- **`social_media_agent.py`** — posts via each platform's official
  API using a token you generate and supply, not a headless browser
  clicking through the normal UI. Browser-driven account automation
  is what most platforms' bot detection exists to catch and is
  against most platforms' terms even for your own account — an
  official-API integration with your own token is just you, posting.

Everything else (`filesystem_watcher`, `process_inspector`,
`driver_controller`, `window_manager_hook`, `registry_monitor`,
`web_agent_core`, `site_navigator`, `data_extractor`,
`session_manager`, `form_filler`) is a straightforward implementation
of what the name says.

## Install

```bash
pip install psutil watchdog keyboard mouse pywin32 ^
    screen-brightness-control pycaw comtypes wmi pyperclip ^
    playwright cryptography requests
playwright install chromium
```

## Wiring into the rest of ULTRON

Each module is standalone and runnable on its own (`python -m
PHASE_17_6_AUTOMATION.DEEP_OS_INTEGRATION.window_manager_hook` etc.)
for quick testing. To hook into the main assistant loop, import the
classes from the package `__init__.py` files and wire their
callbacks (`on_change`, `on_foreground_change`, etc.) into your
existing event/intent router the same way earlier phases did.
