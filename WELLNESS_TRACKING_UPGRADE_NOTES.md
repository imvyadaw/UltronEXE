# Wellness & Fitness Tracking upgrade

## Added
- `wellness/activity_tracker.py` - log steps, water intake (ml), sleep
  hours, workouts (type/duration/notes), and a simple 1-5 mood check-in.
  JSON-backed, same shape as `finance/expense_tracker.py`. Daily and
  7-day rolling summaries.
- `wellness/goal_manager.py` - user-set targets for `steps`, `water_ml`,
  `sleep_hours`, `workouts_weekly`, checked against actuals. Never
  invents a default target - every number comes from the user.
- `wellness/streak_tracker.py` - consecutive-day streaks per daily
  metric, computed on read (no separate storage) by walking
  `activity_tracker`'s history against `goal_manager`'s targets. Handles
  the "today isn't over yet" case: an unmet today doesn't zero out an
  existing streak, it just isn't counted until it's met.
- `wellness/insights_engine.py` - combines all three into one report;
  narrates it via `ai/ai_router.py` when available, with the prompt
  explicitly restricted to goal-progress framing (no weight/diet/body
  commentary, no medical advice). Falls back to raw numbers only if the
  router isn't reachable - same fail-closed pattern as
  `finance/insights_engine.py`.
- `ai/wellness_tools.py` - 8 new tools: `log_steps`, `log_water`,
  `log_sleep`, `log_workout`, `log_mood`, `wellness_goal_set`,
  `wellness_status`, `wellness_insights`.
- `tests/test_wellness.py` - 8 tests: logging + validation for each
  metric, weekly aggregation, goal met/unmet, unknown-metric rejection,
  and streak current/best-streak correctness (including a
  break-then-recover history to prove `best_streak` isn't just the
  current run).

## Wired
- `ai/tools_schema.py` - `TOOLS = TOOLS + WELLNESS_TOOLS`.
- `ai/tool_runtime.py` - `_DIRECT_HANDLERS.update(WELLNESS_DIRECT_HANDLERS)`.
- No `core/assistant.py` change needed - unlike finance's market
  watcher, nothing here has a background scheduler; every tool is a
  plain local read/write.

## Why this and not something else
Same audit approach as the finance upgrade: grepped the whole tree for
`fitness`, `sleep`, `workout`, `journal`, `habit_tracker`, `goal_tracker`
before writing anything. `fitness`/`sleep`/`workout` came back with zero
matches. The only near-miss was `proactive/health_remind.py`, which is a
generic interval-reminder scheduler with **no data storage of its own**
(confirmed by reading it) - it can remind you to log something, but
there was nothing to log to. This fills that gap rather than duplicating
it; `wellness_status`/`wellness_insights` could reasonably call into
`health_remind.py` for nudges in a future pass, but that wasn't done
here to keep this change scoped to tracking itself.

## Safety
- Deliberately out of scope: no calorie counting, no weight tracking, no
  diet targets, no AI-generated numeric health/fitness goals anywhere in
  this module. Every target is user-chosen; Ultron only ever reports
  "did you hit the number you set," never a judgment about the number.
- The insights narration prompt explicitly forbids weight/diet/body
  commentary and medical advice, and is skipped entirely (falls back to
  plain numbers) if the AI router call fails for any reason.
- Purely local JSON state, no wearable/health-app network integration -
  nothing here requests new permissions or touches
  `core/permissions.py`, `approval/`, or `safety/`.

## Not done (be aware)
- No wearable/phone health-app sync (Google Fit / Apple Health) - all
  entries are user-reported (voice/text), same relationship
  `finance/expense_tracker.py` has with bank data.
- `streak_tracker.py`'s lookback is capped at 90 days
  (`MAX_LOOKBACK_DAYS`) for performance - a streak longer than that will
  report a `best_streak` of at most 90 even if the real unbroken run is
  longer. Fine for now; would need a smarter incremental approach if
  someone's genuinely logging goal-meeting activity for 90+ days
  straight.
- `wellness_status`/`wellness_insights` don't yet call into
  `proactive/health_remind.py` for proactive nudges (e.g. "you haven't
  logged water today") - noted above as a natural next step.
