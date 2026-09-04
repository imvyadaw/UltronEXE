# Task 7 - "Email + WhatsApp + phone call bhejna"

## Important finding before wiring anything: 2 of the 3 already work

Checked the existing (already-connected, pre-dating this whole thread's
work) tool set before touching anything, per this project's own
convention of not handing the model two tools that do the same job:

- **Email already sends/reads real mail today.** `agents/email_agent.py`
  is wired to `send_email`/`read_inbox`/`search_emails` and is - line
  for line - the same SMTP/IMAP approach as
  `PHASE_18_7_AUTOMATION/CONNECT/email.py` (same `EMAIL_ADDRESS`/
  `EMAIL_PASSWORD` env vars, same stdlib `smtplib`/`imaplib`).
  **`CONNECT/email.py` was not wired - it would be a pure duplicate.**
  If email sending "isn't working" for you, the fix is configuring
  `EMAIL_ADDRESS`/`EMAIL_PASSWORD` in `.env` (a Gmail *app password*,
  not your normal password), not new code.

- **WhatsApp already sends real messages today, two ways.**
  `skills/communication/whatsapp.py` is wired to
  `send_whatsapp_message`/`send_whatsapp_template`/`send_whatsapp_media`
  (Meta/Twilio Business API - needs `WHATSAPP_ACCESS_TOKEN` +
  `WHATSAPP_PHONE_NUMBER_ID`), and separately
  `apps/communication/whatsapp.py` is wired to
  `whatsapp_send_message`/`whatsapp_send_message_by_name` (drives the
  WhatsApp Desktop app directly, no API credentials needed - this is
  the one to use if you don't want to set up a Meta Business app).
  **`CONNECT/whatsapp.py` was not wired - same reason, pure duplicate**
  of the Business-API path specifically.

- **`ACTIONS/send_message.py`** (the generic coordinate-based
  click+type+Enter fallback) **was also not wired** - it's exactly
  equivalent to the already-existing `mouse_click` + `type_text` +
  `press_key` tools chained together, so it adds no new capability,
  just a fourth name for the same three-step action.

## What was actually new and got wired: `call_phone`

`PHASE_18_7_AUTOMATION/ACTIONS/call_phone.py` had no equivalent
anywhere else in the codebase - genuinely the only new capability in
this batch. Hands a number to the OS's registered `tel:` handler
(Phone Link on Windows 11 with a paired Android phone, or whatever
else is registered). Wired as a new `call_phone` tool in
`core/executor.py` + `ai/tools_schema.py`.

**Safety-gated the same way `shutdown_pc`/`restart_pc`/`kill_process`
already are in this codebase** (matched the existing convention rather
than inventing a new one): the tool requires `confirm: true`; without
it, it returns an error asking for confirmation instead of placing the
call. This means the model can't place a call as a side effect of a
tool-calling loop without an explicit confirmed step - the same
pattern already governing every other consequential action in this
project.

## Verified in this sandbox

- `core/executor.py` and `ai/tools_schema.py` syntax-checked after editing.
- `call_phone` tool logic tested standalone against 3 cases: no
  `confirm` -> correctly refuses with the confirmation-request message;
  `confirm=true` + garbage number -> correctly fails number-format
  validation; `confirm=true` + valid-looking number -> correctly
  attempts the OS handoff (fails gracefully with "no tel: handler
  available" in this headless Linux sandbox, which is expected - a real
  Windows machine with Phone Link configured is needed to verify an
  actual handoff).

---

## Follow-up pass: contacts, Google Calendar, social - and a real bug

Requested as a follow-up: connect whatever else in this batch adds
genuine new capability, and add something new. Two things got
connected because they aren't duplicates of anything already wired,
one new module got built, and one pre-existing systemic bug got found
and fixed along the way.

### New: `agents/contacts_agent.py`

A local SQLite contacts store (add/find/list/delete), same pattern as
`agents/calendar_agent.py`. Exists so `call_phone` can take a saved
contact `name` ("call Mummy") instead of forcing a raw number every
time. `find_contact` matches exact name first, then falls back to a
substring match *only* if exactly one contact matches - an ambiguous
or unknown name fails with a clear error rather than guessing, since a
wrong number handed to `call_phone` is a real-world action.

`call_phone`'s `core/executor.py` handler now resolves `name` -> number
via this agent before calling, but only after its own `confirm`
check - an unconfirmed call never triggers a lookup either.

### Now connected: `google_calendar_list_events` / `google_calendar_create_event`

`CONNECT/calendar.py` (Google Calendar REST API v3) is genuinely
different from the already-wired `agents/calendar_agent.py` - that one
is a local, offline, SQLite-only calendar; this one syncs to the
user's real Google account (readable from their phone too). Not a
duplicate, so it got its own distinctly-named tools instead of being
folded into `add_calendar_event`/`list_calendar_events`. Needs
`GOOGLE_CALENDAR_ACCESS_TOKEN` in `.env`; without it, returns an empty
list / `{"success": False}` rather than erroring.

### Now connected: `post_to_social`

`CONNECT/social.py`'s webhook fan-out (Slack/Discord/Zapier via
`SOCIAL_WEBHOOK_<NAME>` env vars) - also genuinely new, nothing else in
the codebase does this. Still deliberately not native OAuth posting to
Twitter/Instagram/LinkedIn - see that module's own docstring for why.

### Still not connected (unchanged reasoning)

`CONNECT/email.py`, `CONNECT/whatsapp.py`, `ACTIONS/send_message.py`,
`ACTIONS/open_app.py`, `ACTIONS/click_mouse.py`, `ACTIONS/type_text.py`,
`ACTIONS/fill_form.py`, `CONNECT/spotify.py`, `CONNECT/youtube.py` -
every one of these still duplicates a tool that's already wired
elsewhere in the project (see the original section above, plus:
`open_app.py` duplicates `open_application`, `click_mouse.py`
duplicates `mouse_click`, `type_text.py` duplicates the already-wired
`type_text`, `fill_form.py` is just those two chained,
`CONNECT/spotify.py` duplicates `apps/media/spotify.py`'s desktop-app
control, and `CONNECT/youtube.py`'s API-key-requiring search duplicates
`youtube_play`'s key-free scraping approach). Wiring these too would
hand the model two tools for the same job - the exact thing this
project's own convention (see `core/executor.py`'s comments throughout)
avoids.

### Bug found and fixed: `confirm` was silently stripped before reaching tools

While wiring `call_phone`'s central gate, found that
`ai/tool_runtime.py`'s `execute_tool_from_dict()` called
`tool_dict.pop("confirm", False)` to check whether `ActionPipeline`
should require confirmation - which *removes* `confirm` from the
arguments dict before it's ever passed down to `execute_tool_call` ->
`TOOL_ARG_MAP` -> the tool's own handler. Every destructive tool with
its own inline `if not confirm:` check (`shutdown_pc`, `restart_pc`,
`sign_out`, `kill_process`, and now `call_phone`) would therefore
refuse *every single call* through the real model-facing path - even
one immediately after the central gate had already required and
received `confirm: true` - because by the time it reached the tool,
`confirm` had already been stripped back to `False`.

Fixed by changing that one `.pop()` to `.get()`, so `confirm` survives
in the dict all the way down. Verified before/after via
`execute_tool_from_dict({"tool": "call_phone", "number": "...",
"confirm": True})`: before the fix this returned the tool's own
"call again with confirm=true" error even with `confirm: True` already
given; after the fix it correctly proceeds to the OS handoff attempt.
Also spot-checked `shutdown_pc` through the same path to confirm the
fix isn't `call_phone`-specific.

Also added `call_phone` to `core/permissions.py`'s `DESTRUCTIVE_TOOLS`
(it was missing, so only its own inline check was gating it - not the
central `ActionPipeline` one every other real-world action gets) and
to `ai/tool_runtime.py`'s `TOOL_ARG_MAP` (it was declared in
`ai/tools_schema.py` and wired in `core/executor.py`'s `tool_map`, but
had no entry here - meaning `execute_tool_call` rejected every call
with `"Unknown tool: call_phone"` before ever reaching
`core/executor.py`, the same bug class as the 16 missing entries found
in the earlier Phase 1-29 audit).

## Verified in this sandbox (follow-up pass)

- Full project syntax-compiled: 1004 `.py` files, 0 errors.
- Existing test suite: 211 passed, 2 skipped (no regressions).
- `agents/contacts_agent.py` unit-tested standalone: add/find (exact,
  ambiguous, unique-substring, no-match)/list/delete all correct.
- Every new/fixed tool tested end-to-end through both
  `core.executor.execute_tool` and the real model-facing
  `ai.tool_runtime.execute_tool_from_dict` path: `call_phone` (by
  number, by name, unconfirmed, confirmed, unknown name),
  `add_contact`/`find_contact`/`list_contacts`/`delete_contact`,
  `post_to_social` (fails cleanly with no webhooks configured),
  `google_calendar_list_events`/`google_calendar_create_event` (fail
  cleanly with no access token configured).
- Confirmed `shutdown_pc` no longer gets stuck re-asking for
  confirmation after already receiving `confirm: true`.

