# Task 8 - dormant-module audit (84 top-level packages) + wiring

## How the audit was done

Re-ran the reachability check from scratch against this
`ultron_project_COGNITIVE_WIRED` snapshot (84 top-level packages under
the project root) rather than trusting the older `docs/TASK6_DORMANT_AUDIT.md`
numbers, since the project has been restructured multiple times since
that doc was written.

Method: AST-based import graph BFS from `main.py`, catching both plain
`import`/`from X import Y` and `importlib.import_module()`/`__import__()`
calls with literal string arguments. Static BFS alone flagged 15
top-level packages as unreached. Each of those 15 was then manually
verified with `grep -rn "<pkg>\." .` (outside the package's own files)
to rule out **dynamic** dotted-path imports the static pass can't see
(the codebase's own "lazy singleton, string-keyed registry" pattern -
see `ai/apps_tools.py`'s `APP_REGISTRY` - resolves module paths at
runtime via `importlib.import_module(module_path)` where `module_path`
is a dict *value*, not a literal argument, so a naive AST scan misses
it entirely).

## Result: the static BFS had 11 false positives

| Package | Verdict |
|---|---|
| `apps` | **False positive.** Already fully wired via `ai/apps_tools.py`'s `APP_REGISTRY` (61 apps, dynamic `importlib.import_module`) - confirmed by reading `apps/__init__.py`'s own docstring and `ai/apps_tools.py`'s `_get()`. |
| `certification`, `deep_verification`, `tools`, `verification_engine` | **Not product features.** QA/CLI harnesses meant to be run directly (`python tools/scan_all_apps.py`, pytest fixtures importing `certification`/`deep_verification`/`verification_engine`) - `grep` confirms every reference to these is from `tests/` or from each other, never from anything in the live app's import chain. Correctly unreached from `main.py` by design; no AI-tool wiring makes sense for them. |
| `mcp_server`, `test2`, `scripts`, `testing`, `tests`, `""` (loose root files) | Separate entry points / test infrastructure, not meant to be imported by `main.py`. Not gaps. |

## Result: 4 genuine dormant packages, confirmed by zero cross-references

`networking/`, `perception/`, `scenarios/`, `scheduler/` - each verified
via `grep -rn "<pkg>\." .` outside its own folder: **zero hits**, in
every case. All four are complete, working code (every file
syntax-checked, no stub markers, no `NotImplementedError`) that nothing
in the live app ever called.

## What was wired this task

New files, same pattern as every prior `ai/*_tools.py` (duplicated
`_tool()` helper to avoid a circular import, lazy-singleton getters,
a `*_TOOLS` list + `*_DIRECT_HANDLERS` dict, merged at the bottom of
`ai/tools_schema.py` / `ai/tool_runtime.py`):

- **`ai/networking_tools.py`** (20 tools) - `networking/http_client.py`
  (stateless GET/POST/PUT/DELETE to any URL), `ssh_client.py` and
  `ftp_client.py` (session-keyed connect/run/upload/download/close,
  same lazy-dict-by-key pattern as `ai/apps_tools.py`), `websocket.py`
  (session-keyed connect/send, incoming messages buffered and drained
  via `websocket_get_messages`).
- **`ai/perception_tools.py`** (5 tools) - only the **one-off**
  snapshot/analyze/detect calls from `perception/`:
  `get_activity_snapshot`, `detect_text_emotion`, `analyze_screen`,
  `locate_on_screen`, `get_system_perception_snapshot`.
- **`ai/scenarios_tools.py`** (4 tools) - `get_morning_briefing`,
  `get_evening_summary`, `check_meeting_reminders`,
  `check_work_break_status`, each returning both the structured data
  and (where the class has one) the ready-to-speak `briefing_text()`.
- **`ai/scheduler_tools.py`** (5 tools) - `schedule_tool_in/at/recurring`
  (wraps `scheduler/background_tasks.py`'s `submit_later/at/recurring`),
  `get_scheduled_task_status`, `cancel_scheduled_task`. This closes a
  gap one level deeper than the wrapper itself: neither
  `core/scheduler.py` nor `core/task_queue.py` had **any** AI-tool
  entry before this (`grep -rln` across `ai/*.py` for either module
  came back empty) - the model had no way to say "run this tool later"
  at all, wrapper or not.

**34 new tools total**, cross-checked live (imported every new module,
compared each `*_TOOLS` list's names against its `*_DIRECT_HANDLERS`
dict): **34/34 match, 0 gaps** - the "declared in schema but no
dispatch entry" bug class from every earlier audit in this project
does not recur here.

## Deliberately NOT wired (needs your explicit go-ahead first)

Same standard as `docs/TASK6_DORMANT_AUDIT.md` set for continuous/
higher-sensitivity capability:

1. **`perception/*.py`'s `start_polling()`/`stop_polling()`** on
   `ActivityMonitor`, `SystemListener` (and the equivalent always-on
   pattern implied for voice/screen) - turning "check right now" into
   an always-on background watcher is a materially different
   capability from the on-demand snapshot calls that were wired.
2. **`perception/voice_processor.py`'s `listen_and_process()`** - opens
   the mic itself. Wiring it would give the model a second way to
   start listening alongside the existing wake-word pipeline that
   already owns that decision. Composite value (transcript + speaker
   ID + emotion in one call) is real but out of scope this pass.

## Bug found and fixed while testing the new wiring

`scheduler/background_tasks.py`'s `status()` method looked for a
`"scheduled"` key holding a list of `{"task_id": ...}` dicts in
`Scheduler.list_scheduled()`'s return value - but
`core/scheduler.py::list_scheduled()` actually returns
`{"count": N, "tasks": {task_id: {...}}}` (a **dict keyed by
task_id**, key `"tasks"` not `"scheduled"`). The mismatched key meant
`.get("scheduled", [])` always fell back to an empty list, so
`get_scheduled_task_status` silently returned `{"status": "not_found"}`
for every task - even one confirmed still active (reproduced: called
`cancel_scheduled_task` on the same `task_id` right after a
`"not_found"` status and it succeeded, proving the task really was
still scheduled). Fixed to read the real dict shape directly. Verified
live: schedule a task -> status now correctly returns
`{"status": "scheduled", ...}` -> cancel -> status now correctly
returns `{"status": "not_found"}`.

## Verified in this sandbox

- Full project syntax recompile: 1267 files, 0 errors.
- `networking_tools`/`perception_tools`/`scenarios_tools`/`scheduler_tools`
  schema-vs-dispatch cross-check: 34/34 tool names present in both,
  0 gaps.
- Live end-to-end calls (real, non-mocked) through every new handler
  that doesn't need Windows-only APIs or a real external
  host/credential: `schedule_tool_in`/`get_scheduled_task_status`/
  `cancel_scheduled_task` (full round trip, including the bug above),
  `http_get` (real network call, sandbox has no outbound access so it
  returned a real `403`/connection-shaped error rather than a crash),
  `ssh_run_command` on a nonexistent session (correct "no session,
  call ssh_connect first" error, not a crash), `detect_text_emotion`,
  `get_system_perception_snapshot`, `get_activity_snapshot`,
  `check_work_break_status`, `check_meeting_reminders`,
  `get_morning_briefing` (all fail-soft correctly with no calendar/
  weather backend configured in this sandbox, same "optional data
  source, shorter but still useful" contract documented in each
  scenario module's own docstring).
- Existing test suite: 232 passed, 1 skipped, 0 new failures (the one
  failing node, `test_release_has_no_runtime_or_secret_artifacts`, is
  the same pre-existing packaging-hygiene check noted in this
  project's very first ground-truth brief - it fails only when
  `pytest` itself regenerates `__pycache__`/runtime `.db` files by
  running, which is expected and not a real defect; this delivery zip
  had all of that swept before packaging).
- **Not verified**: `ssh_connect`/`ftp_connect`/`websocket_connect`
  against a real host (need real credentials/endpoints -
  `paramiko`/`websocket-client` also aren't installed in this
  sandbox), and `locate_on_screen`/`analyze_screen`'s vision-LLM tier
  (needs `GEMINI_API_KEY` + a real screen). Same "test on your actual
  machine" note as every prior task in this thread.
