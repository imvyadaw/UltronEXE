# Task 4 changelog - wire the dormant Phase 18 "brain" into the live app

## Integration shape chosen: (a) - observer layer, not router

Chosen over (b) because the overlap map
(`docs/PHASE18_INTEGRATION_MAP.md`) found a genuine, if narrow, conflict:
`decision_maker`'s `GOAL_PATTERNS` ("goal: ...", "handle X end to end")
would intercept a class of input the live pipeline currently treats as
ordinary chat, and route it to `autonomous_executor` instead - a real
behavior change, not just additional bookkeeping. `consciousness.py` and
`personality.speak()`, by contrast, are either genuinely read-only or
narrowly applicable to lines that already have a matching phrase category,
so they could be added with no change to *which* tier handles *which*
input. Per the task's own recommendation, (a) ships first; (b) is left for
a future task once (a)'s consciousness data (confidence trend, setback
rate) gives a real basis for deciding whether the larger rewrite is worth
it.

## Files changed

### `core/assistant.py`
- `Assistant.__init__()`: added a best-effort `self.consciousness` /
  `self.personality` connection (Phase 18 observer layer), degrading to
  `None`/`None` exactly like the existing `self.intelligence` block does
  on an incomplete checkout. Added `self._start_proactive_alerts()` call.
- `Assistant._handle_command_inner()`: the original 6-tier routing body
  was moved verbatim into a new `Assistant._route_turn()` method (no
  logic changes inside it beyond the `_note_outcome()` calls below);
  `_handle_command_inner()` now wraps a call to `_route_turn()` in
  `consciousness.push_focus(user_input)` / `pop_focus()` via
  `try`/`finally`, so a still-active focus never gets left on the stack
  if a tier raises.
- `Assistant._route_turn()`: one `self._note_outcome(satisfied=...)` call
  added at each of the method's existing return points (control command,
  slash command, local system command, fast tier, intent-router-handled,
  and the final tier-4 LLM path using the existing `_call_failed`
  before/after `last_error` comparison). No return values, control flow,
  or tier ordering changed.
- `Assistant._on_background_task_done()`: announcement text now gets a
  `personality.speak("general_ack"/"general_concern")` lead-in, and
  reports outcome via `_note_outcome()`.
- New methods: `Assistant._personality_lead_in()`, `Assistant._note_outcome()`,
  `Assistant._start_proactive_alerts()` (see map doc for what each does).

### `ai/local_router.py`
- New `_introspection_reply()` helper: reads
  `PHASE_18_1_CORE_FOUNDATION.CORE.consciousness.get_consciousness().reflect()`
  and formats a short status sentence (focus / confidence / stacked
  interruptions / active background tasks / recent setbacks). Returns
  `None` if the observer layer isn't importable, so the caller falls
  through to the LLM exactly as this query would have been handled
  before this task.
- `route_system_command()`: new regex branch (checked before the
  time/date branches, no functional overlap with them) matching "what
  are you doing right now", "what's your status", "status report", "are
  you busy/idle" - answered locally via `_introspection_reply()` when
  available.

### New files
- `docs/PHASE18_INTEGRATION_MAP.md` - the Step 1 tier-by-tier map.
- `docs/TASK4_CHANGELOG.md` - this file.

### Not touched
`ai/tool_runtime.py`, `core/executor.py`, anything under the Phase 2B
tool-reliability work, `proactive/engine.py` and the rest of
`proactive/` beyond `triggers/threshold_alerts.py`, and every file under
`PHASE_18_1_CORE_FOUNDATION/` itself (used as-is, not modified) except
where noted above.

## Test results

`core/assistant.py` and `ai/local_router.py` were syntax-checked
(`ast.parse`) and pass. The Phase 18 modules this task actually calls
(`consciousness.py`, `personality.py`, `proactive/triggers/threshold_alerts.py`)
were exercised standalone in this sandbox and behave as documented
(`push_focus`/`pop_focus`/`note_outcome`/`reflect()` round-trip correctly;
`personality.speak()` returns the expected canned lines for `general_ack`
and `cpu_high`; `ThresholdAlerts.check()` runs cleanly against this
sandbox's real CPU/RAM/disk via `psutil` and returns `[]` when nothing is
over threshold, as expected).

**Full end-to-end verification (running `main.py` in any mode, or the
`testing/`/`PHASE_29_*` suites) could not be performed in this sandbox**:
`core/executor.py` imports the `windows` package (`pywinauto`-backed),
which is Windows-only - this is a pre-existing constraint of the project,
not something introduced by this task, and it means `ai/local_router.py`
(and therefore `core/assistant.py`) cannot be imported end-to-end on this
Linux sandbox either before or after these changes. The logic added here
was verified by (1) syntax-checking every changed file, (2) exercising
the actual Phase 18/proactive modules standalone as described above, and
(3) tracing every new/changed call path by hand against the surrounding
code. **Please run the real suite
(`testing/unit`, `testing/integration`, `testing/e2e`,
`PHASE_29_A_STABILITY`/`PHASE_29_B_HARDENING`/`PHASE_29_C_CERTIFICATION`)
and a manual smoke test of all `main.py` entry modes on a Windows
checkout before merging**, and compare the certification suite's
PASS/BLOCKED verdicts against `PHASE_29_C_CERTIFICATION/reports/last_run_report_linux_sandbox.json`
as the task instructions describe - that comparison genuinely needs a
working `core.executor` import, which this environment doesn't have.
