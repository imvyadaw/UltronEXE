# Task 6 - full dormant-code audit + Phase A wiring

## How the audit was done

For every top-level package (25 `PHASE_*` folders plus `agents/`,
`execution/`, `intelligence_bridge/`, `perception/`, `plugins/`,
`router/`, `scenarios/`, `skills/`, `vision/`), grepped the entire repo
for `from <pkg>` / `import <pkg>` **outside that package's own files**.
A zero count means nothing anywhere else in the codebase ever imports
it - it's a fully isolated island, unreachable from `main.py` no matter
how deep you follow imports.

11 packages came back at zero:

| Package | Files | Lines | External deps needed | Risk if wired |
|---|---|---|---|---|
| `PHASE_17_3_MEMORY_SYSTEM` | 7 | 1522 | none | Low - **likely duplicates the already-wired `memory/` package** (episodic/semantic/procedural/emotional memory tools already exist via `agents/*_agent.py` - see core/executor.py `_get()`). Not wired this task; needs a dedup pass against `memory/` first, not a blind add. |
| `PHASE_17_5_HUMAN_INTERACTION` | 18 | 2186 | none beyond project's own vision/voice/ui packages | Medium (screen vision, voice emotion, adaptive UI) - not wired this task, out of scope |
| `PHASE_17_6_AUTOMATION` | 15 | 1941 | `playwright`, `keyboard`, `mouse` | **High** (global keyboard/mouse hooks, registry monitor, web automation incl. `captcha_solver.py`) - **not wired, needs your explicit go-ahead** |
| `PHASE_17_8_PLATFORM` | 12 | 1906 | `websockets`, `pyyaml` | **High** (`SKILL_CREATOR/` can generate and auto-deploy its own new code) - **not wired, needs your explicit go-ahead** |
| `PHASE_17_9_SECURITY` | 6 | 887 | none | Low (defensive/audit-only) - not wired this task, out of scope |
| `PHASE_17_10_ANALYTICS` | 5 | 674 | `pySMART` | Low (read-only dashboard) - not wired this task, out of scope |
| `PHASE_18_6_AI_AGENTS` | 6 | 758 | none | Low-medium - **wired this task** (5 of 6 personas; `coder.py` skipped, see below) |
| `PHASE_18_7_AUTOMATION` | 12 | 1215 | none | **Highest** (`CONNECT/email.py` sends real email, `CONNECT/whatsapp.py` sends real WhatsApp messages via Meta's API, `ACTIONS/call_phone.py` places calls) - **not wired, needs your explicit go-ahead**, see `docs/TASK6_DORMANT_AUDIT.md`'s "What's still NOT wired" below |
| `PHASE_18_9_2_SELF_MANAGEMENT` | 12 | 1137 | none | Low (all bookkeeping - HEAL/*.py never executes a fix itself, PROACTIVE/*.py just compiles items other callers file) - **wired this task** |
| `perception/` | 5 | 682 | project's own vision/voice/proactive/memory packages | Medium (screen/emotion monitoring) - not wired this task, out of scope |
| `scenarios/` | 4 | 503 | project's own conversation/proactive/skills/ui packages | Low-medium - not wired this task, out of scope |

Every file in every one of these 11 packages was syntax-checked
(`ast.parse`) - **all pass, nothing is broken or incomplete code.**
The only reason any of it doesn't run is that nothing calls it.

## What was wired this task (Phase A - low risk, no new external action capability)

### `PHASE_18_9_2_SELF_MANAGEMENT` (all of it)
- `HEAL/health_check.py`, `HEAL/auto_fix.py`, `HEAL/restart.py`,
  `HEAL/update_self.py` - a status board + fix-suggestion log + restart/
  update history. None of these four modules execute anything
  themselves (each one's own docstring says so, verified by reading the
  code) - they only record what some other, already-existing part of
  the app reports.
- `PROACTIVE/morning_brief.py`, `evening_wrap.py`, `health_remind.py`,
  `meeting_prep.py`, `travel_alert.py` - same-day item compilers. What
  goes into a brief is filed by other tool calls (e.g.
  `upcoming_calendar_events`, `list_todos`) - these modules just hold
  and order whatever's filed.

### `PHASE_18_6_AI_AGENTS` (5 of 6 personas)
`analyst.py`, `researcher.py`, `teacher.py`, `writer.py`, `guard.py`.
**`coder.py` deliberately skipped** - its `generate()`/`review()`/
`explain()` are near-duplicates of the already-wired `write_code`/
`review_code`/`explain_code` tools (`windows/__init__.py`, confirmed by
reading both). Wiring it in too would just give the model two tools
that do the same thing.

**27 new tools total**, added to `core/executor.py`'s `_get()`
singleton factory + `tool_map`, and `ai/tools_schema.py`'s `TOOLS` list
(new `PHASE18_TOOLS` block, appended the same way `VISION_LLM_TOOLS`
already was) - every name cross-checked present in both files (script
run, all 27 confirmed).

**None of Phase A adds any capability the model didn't already
effectively have** - it's health/fix/restart/version bookkeeping,
brief/reminder/meeting/trip note-taking, and read-only text analysis/
research/teaching/writing/content-review personas. Nothing here sends
a message, executes a fix, controls the OS, or touches a new device/
credential.

## What's still NOT wired (needs your explicit go-ahead first)

These were deliberately left disconnected because they can take
consequential real-world action, not because anything is broken:

1. **`PHASE_18_7_AUTOMATION/CONNECT/email.py` + `whatsapp.py`** - real
   SMTP send / real WhatsApp Business API send. Gated behind
   `EMAIL_ADDRESS`/`EMAIL_PASSWORD` and
   `WHATSAPP_ACCESS_TOKEN`/`WHATSAPP_PHONE_NUMBER_ID` env vars, so
   nothing happens without you configuring credentials either way - but
   wiring the tool in is the step that lets the model decide to use them.
2. **`PHASE_18_7_AUTOMATION/ACTIONS/call_phone.py`,
   `send_message.py`** - places a phone call / sends a message via
   whatever's on-screen.
3. **`PHASE_17_6_AUTOMATION`** - global keyboard/mouse hooks
   (`global_hook_manager.py`), Windows registry monitoring
   (`registry_monitor.py`), and web automation including a CAPTCHA
   solver (`captcha_solver.py`) and a social-media agent
   (`social_media_agent.py`).
4. **`PHASE_17_8_PLATFORM/SKILL_CREATOR/`** - `skill_code_generator.py`
   + `auto_deployer.py` can generate new Python code and deploy it into
   the running app on their own.
5. **`PHASE_17_5_HUMAN_INTERACTION/COMPUTER_VISION/`** and
   **`perception/`** - continuous screen/voice/emotion monitoring.
6. **`PHASE_17_3_MEMORY_SYSTEM`** - not necessarily risky, but needs a
   dedup pass against the already-wired `memory/` package first (see
   table above) so we don't hand the model two different "remember
   this" tools that write to different stores.

Tell me which of these (if any) you want wired next, and I'll do the
same treatment: read the actual code, check for collisions with what's
already connected, wire it, test what's testable standalone, and
document the risk plainly before you turn anything real-world-facing on.

## Verified in this sandbox

- All 11 dormant packages: every `.py` file syntax-checked, all pass.
- External pip dependency scan per file (see table above).
- `core/executor.py` and `ai/tools_schema.py` syntax-checked after
  editing.
- All 27 new tool names cross-verified present in both
  `tool_map` (executor) and `TOOLS` (schema) - the consistency
  `ai/tools_schema.py`'s own docstring requires.
- Standalone functional test (bypassing the Windows-only import chain,
  same constraint as every prior task): `health_check.report()` +
  `.run_check()`, `morning_brief.add_item()` + `.generate_brief()`, and
  `AnalystAgent.analyze_numbers()` all ran and returned correct,
  real (non-mocked) results.
- **Not verified**: the LLM-calling agent methods (`researcher.py`,
  `teacher.py`, `writer.py`'s draft/rewrite, `analyst.py`'s
  interpretation path) - these go through `ai/ai_router.py` the same
  as everything else, so they need a real `GROQ_API_KEY` and the
  Windows-capable import chain to test end-to-end. Same "test on your
  actual machine" note as every prior task in this thread.
