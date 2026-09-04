# Phase 18 <-> live pipeline overlap map (Task 4)

Read alongside: `core/assistant.py::Assistant._handle_command_inner()` /
`_route_turn()`, `PHASE_18_1_CORE_FOUNDATION/CORE/brain.py::Ultron.think()`,
`PHASE_18_1_CORE_FOUNDATION/CORE/decision_maker.py::DecisionMaker.decide()`,
`PHASE_17_2_COGNITIVE_BRAIN/COGNITIVE_CORE/intent_resolver.py::route()`.

## Tier-by-tier

| `_route_turn()` tier | What decides it | `decision_maker.decide()` branch it corresponds to | Conflict? |
|---|---|---|---|
| 1. Control commands (mode toggles) - `local_router.check_control_command()` | Fixed regex table in `ai/local_router.py`, no LLM | None - `decision_maker` never sees this text category at all; it isn't routed through `intent_resolver.classify()`'s underlying `core.intent_router.classify()` in a way that would match it, and control commands never look like a "goal:"/"handle X end to end" phrasing either. | No overlap. Purely additive slot for consciousness bookkeeping. |
| 2. Slash commands (`/help`, `/reset`, ...) - `self.processor` | `self.processor.is_command()`/`.process()`, no LLM | None, same reasoning as tier 1 - slash commands never reach `intent_resolver`. | No overlap. |
| 3. Local system commands (time/date/volume/open-app) - `local_router.route_system_command()` | Fixed regex + tool table in `ai/local_router.py` | None - this table is entirely separate from `core.intent_router`/`intent_resolver`, which `decision_maker` sits on top of. A "what time is it" never reaches `decision_maker.decide()` in the current app either. | No overlap. This is also where the new `_introspection_reply()` status query was added (see below) - itself has no `decision_maker` equivalent, so it's additive too. |
| 3.5 Named workflows / background tasks - `intent_router.classify()` + `.route()` (this is `core/intent_router.py`, **not** `PHASE_17_2`'s `intent_resolver.py`) | `core/intent_router.py`'s own regex patterns for WORKFLOW / BACKGROUND / TASK_STATUS / LIST_TASKS | `decision_maker.decide()`'s `"delegate"` route, **exactly** whenever `intent_resolver.classify()`'s fallback (`core.intent_router.classify()`) matches something - `intent_resolver.classify()` literally re-uses the same `core.intent_router.classify()` call the live app already made. | No genuine conflict - it's the same classifier being asked twice, so it always agrees with itself. (Redundant compute if `decision_maker` were wired in, not a behavioral conflict.) |
| 3.6 Complexity router ("normal" tier, chat-only, tool-free) - `ai/complexity_router.classify()` | Only reached when `intent_router.classify(...).intent == "chat"` | `decision_maker.decide()`'s `"delegate"` route **unless** the text also matches one of `intent_resolver.GOAL_PATTERNS` (`"goal: ..."`, `"handle X end to end"`, `"X khud se kar do"`, etc.), in which case `decision_maker` would instead pick `"goal_quick"`/`"goal_full"`/`"clarify"`. | **Real conflict, narrow scope.** Today, text matching `GOAL_PATTERNS` is just ordinary chat to the live app and goes through tiers 3.6/4 like anything else. If `decision_maker` were wired in as an actual router, that same text would instead be pulled out and handed to `autonomous_executor`'s multi-step plan/execute/critique loop - a different code path with different side effects (it can call tools on its own, across several LLM round-trips) for the same input. This is the one class of input where the two systems would genuinely disagree about what should happen. |
| 4. Full tool-calling loop - `self.client.chat_with_tools()` | Reached for everything tier 3.6 didn't handle | Same `GOAL_PATTERNS` overlap as 3.6 - this is where `GOAL_PATTERNS`-matching text actually ends up today. | Same conflict as 3.6, same narrow scope. |

## Consciousness (`consciousness.py`) - purely additive

`ConsciousnessState` is read-only with respect to everything it reports on
(its own docstring says so, and the code matches: `push_focus`/`pop_focus`/
`note_outcome` only append to in-memory structures, they never call a tool
or change control flow). It can wrap *any* of the six tiers above without
touching which tier handles which input. This is what was wired in for
this task - see `Assistant._handle_command_inner()`/`_route_turn()` and
the `_note_outcome()` calls at each tier's return point.

## Personality (`personality.py`) - additive, but narrower than it sounds

`PersonalityProfile.speak(category, **kwargs)` is a **canned-line picker**,
not a rewriter of arbitrary text: `tone_manager.get_phrase()` chooses a
random template from a fixed bank for `category`
(`proactive/personality/ultron_phrases.py`) and only falls back to
formatting `kwargs["message"]` into a generic `"Sir, {message}."` sentence
when that category has **zero** templates. None of the categories that
exist today (`cpu_high`, `memory_high`, `general_ack`, `general_concern`,
etc.) are empty, so passing arbitrary free text via `message=` to an
existing category is silently ignored in favor of a random canned line for
that category.

Two consequences for this integration:

- It is **not** a fit for tier 4's actual LLM answer (a multi-sentence,
  arbitrary-content reply) - there's no way to make `speak()` say that
  specific text, only to pick a category's canned line. This task does not
  route tier 4's response through `personality.speak()`, contrary to what
  a literal reading of "route final responses through personality.speak()
  for tone" might suggest; doing so would replace the actual answer with
  an unrelated canned line.
- It **is** a good fit for the handful of Ultron-initiated lines that
  already have (or can reasonably be given) a matching category:
  background-task-done announcements (`general_ack`/`general_concern`,
  wired in this task) and the new proactive threshold alerts
  (`cpu_high`/`memory_high`/`disk_high`/`battery_low`/`battery_critical`/
  `network_down`/`network_restored` - all pre-existing categories, wired
  in this task).

**Pre-existing latent issue found while tracing this (not fixed - lives
entirely inside code this task did not wire into the live app):**
`decision_maker.py::DecisionMaker._clarify_question()` calls
`personality.speak("general_concern", message=f'...specific goal text...')`
expecting that message to appear in the output. Per the mechanism above,
`"general_concern"` has 3 non-empty templates, so `kwargs["message"]` is
silently dropped and a generic canned line is returned instead of the
goal-specific clarifying question. This only affects `decision_maker`'s
`"clarify"` route, which is not reachable from the live app under
integration shape (a) (`decision_maker.decide_and_execute()` is never
called - see "What was not wired in" below), so it does not affect
current behavior; flagging it for whoever eventually tackles shape (b).

## What was wired in (integration shape (a) - observer, not router)

1. `Assistant.__init__()`: best-effort connect to
   `PHASE_18_1_CORE_FOUNDATION.CORE.consciousness.get_consciousness()` and
   `...personality.get_personality()`, same try/except-degrade pattern
   already used for the Phase 19-20 `intelligence` layer.
2. `Assistant._handle_command_inner()`: the original 6-tier body was moved
   unchanged into a new `_route_turn()` method; `_handle_command_inner()`
   now just does `push_focus(user_input)` / calls `_route_turn()` /
   `pop_focus()` in a `try`/`finally` around it, plus one `_note_outcome()`
   call at each of `_route_turn()`'s existing return points (`satisfied=True`
   for every locally-handled tier, `satisfied=not _call_failed` for the
   tier-4 LLM path, using the existing `last_error` before/after comparison
   that was already there for `_intel_record_call()`).
3. `Assistant._on_background_task_done()`: the announcement text now gets a
   `personality.speak("general_ack"/"general_concern")` lead-in line, and
   reports its outcome to consciousness via `_note_outcome()`.
4. `ai/local_router.py`: one new regex-matched, LLM-free query
   ("what are you doing right now", "what's your status", "status
   report", "are you busy/idle") answered from
   `consciousness.reflect()` via a new `_introspection_reply()` helper.
   Falls through to the LLM unchanged if the observer layer isn't
   available (same degrade-safe contract as every other tier-3 branch).
5. One proactive trigger: `proactive/triggers/threshold_alerts.py`'s
   already-built, already-cooldown-managed `ThresholdAlerts.check()`,
   polled every 60s on its own daemon thread
   (`Assistant._start_proactive_alerts()`), phrased via
   `personality.speak()` and surfaced through `ui.notifications.notify()`
   plus `speak_reply()`. Deliberately not the full `proactive.engine`
   (predictor/suggester/automatic_actions/disruption_guard are untouched).

## What was deliberately NOT wired in

- `decision_maker.decide_and_execute()` / `Ultron.think()` are not called
  anywhere in the live app. Wiring either in would mean the
  `GOAL_PATTERNS` conflict above becomes live (a second system deciding
  to run `autonomous_executor` on input tier 3.6/4 would otherwise have
  answered as chat) - that's shape (b)'s job, not this task's.
- `proactive.engine`, `proactive.predictor`, `proactive.suggester`,
  `proactive.automatic_actions`, `proactive.disruption_guard` remain
  unstarted.
- `ai/tool_runtime.py`, `core/executor.py`, and anything from the Phase 2B
  tool-reliability work were not touched.
