# Task 5 - activating Phase 18's goal-decision layer (autonomy)

## What changed vs the Task 4 handoff

Task 4 deliberately kept `decision_maker`/`autonomous_executor` disconnected
(shape (a) - observer only) because wiring them in as a router meant Ultron
could take independent action on a narrow class of input
(`intent_resolver.GOAL_PATTERNS`: `"goal: ..."`, `"handle X end to end"`,
`"X khud se kar do"`). This task activates that path, at the user's
explicit request, behind an opt-in flag.

## How it's gated

`.env`:
```
ULTRON_AUTONOMY_ENABLED=false   # default - OFF
```
Set to `true` to enable. `Assistant.__init__()` only imports and connects
`decision_maker` when this is set; if unset (or the import fails for any
reason), `self.decision_maker` stays `None` and the app behaves exactly
as it did after Task 4 - no behavior change at all unless you opt in.

## What actually happens when it's ON

In `core/assistant.py::_route_turn()`, a new tier 3.55 sits between the
existing intent-router classification and the fast-tier/full-tool-loop
tiers:

- `decision_maker.decide_and_execute(user_input)` is called **only** when
  `structural.intent == "chat"` (i.e. only on the same fallback bucket
  tier 3.6 already operates on - workflows, background tasks, slash
  commands, control commands are untouched, exactly as documented in
  `PHASE18_INTEGRATION_MAP.md`).
- Internally, `decision_maker.decide()` re-classifies the text itself
  (`intent_resolver.classify()`) and returns `"delegate"` for anything
  that isn't the narrow `GOAL_PATTERNS` phrasing above. When it's
  `"delegate"`, tier 3.55 does nothing and falls straight through to
  3.6/4 - **ordinary chat is unaffected either way, on or off.**
- Only for text that explicitly says `"goal: ..."` / `"handle X end to
  end"` / etc. does this tier take over, in one of three ways:
  - **`clarify`** - Ultron asks one question back instead of guessing
    (happens when consciousness's trailing confidence is low *and* the
    goal text itself is short/ambiguous).
  - **`goal_quick`** - a single-action goal: one plan, one execution
    pass, one critique.
  - **`goal_full`** - a multi-action goal: sub-goal decomposition, each
    sub-goal retried up to `MAX_SUBGOAL_ATTEMPTS=2` times against
    critique feedback.

## Bounds already built into `autonomous_executor.py` (unchanged, verified present)

- `MAX_TOTAL_STEPS = 40` - hard ceiling on tool calls across one goal,
  regardless of sub-goals/retries. Once hit, execution stops and reports
  `"stopped_reason": "step_ceiling_reached"` rather than continuing.
- `MAX_SUBGOAL_ATTEMPTS = 2` - a sub-goal that keeps failing critique
  stops retrying after 2 attempts, not indefinitely.
- Every actual tool call still goes through `core.executor.execute_tool`
  (the same function every other tier already uses) - the goal layer
  gains no capability the tool schema didn't already expose, it only
  adds judgement about *when* to retry/stop.
- `run_goal()` never raises - failures degrade to a returned
  `{"error": ...}` entry, matching the rest of the app's error handling.

## What this means practically - read before enabling

With this on, saying something like `"goal: clean up my Downloads
folder and email me a summary"` will make Ultron **call real tools on
its own across multiple steps without asking for confirmation at each
step** - e.g. file operations, opening apps, and (via `ai/tools_schema.py`
and friends) anything else exposed to the tool-calling layer. It is
bounded (see above) but it is not zero-risk: a wrong LLM-generated plan
can still do something you didn't intend, faster than you can interrupt
it by voice ("stop"/"cancel" still works mid-turn the same as always,
but a step already dispatched to `core.executor.execute_tool` before you
say it will still complete).

**Recommendation:** enable it, then test with clearly low-stakes goals
first (e.g. `"goal: list what's in my Downloads folder"`) before trusting
it with anything destructive, and watch `PHASE_18_1_CORE_FOUNDATION`'s
consciousness confidence (via the "what are you doing right now" status
query added in Task 4) to see how often `outcome.satisfied` is actually
coming back true for your setup.

## Verified in this sandbox (logic only - see the "could not verify" note below)

- `decision_maker.decide()` tested standalone against 4 inputs: two
  ordinary-chat sentences both correctly returned `"delegate"`; `"goal:
  reorganize my downloads folder"` and `"handle my inbox cleanup end to
  end"` both correctly returned `"goal_quick"` and did **not** return
  `"delegate"`.
- `Assistant._response_for_decision()`'s formatting logic tested
  standalone against all four outcome shapes (`clarify`, satisfied,
  unsatisfied/stopped, error) - each produces the expected sentence,
  personality lead-in included.
- `core/assistant.py` syntax-checked after every edit.

**Not verified** (same constraint as Task 4): actually running
`decide_and_execute()` end-to-end - which calls the real LLM
(`goal_planner`/`task_decomposer`/`self_critique_agent`, all via
`ai/ai_router.py`) and real tools (via `core/executor.py`, which imports
the Windows-only `windows`/`pywinauto` package) - is not possible in this
Linux sandbox, with or without a `GROQ_API_KEY`. **Test this on your
actual Windows machine, with `GROQ_API_KEY` set, before relying on it,**
starting with the low-stakes goal suggested above.
