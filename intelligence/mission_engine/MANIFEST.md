# Mission Engine (P1 - Mission Persistence Engine)

## What it does
Persists long-running, multi-session user objectives ("missions") to
`database/missions.db` so they survive a restart/crash, and offers
auto-resume: on the next run, if a mission was left idle mid-way, the
user is told about it instead of having to re-explain themselves.

## Files
- `mission_store.py` - sqlite CRUD (missions / mission_checkpoints / mission_events)
- `mission_manager.py` - lifecycle API + `startup_brief()` / `get_resumable_mission()`

## Wired into
- `core/executor.py` - `_get("mission_manager")` singleton + tool_map entries:
  `create_mission`, `checkpoint_mission`, `list_active_missions`,
  `get_resumable_mission`, `resume_mission`, `pause_mission`,
  `complete_mission`, `abandon_mission`
- `ai/p1_engine_tools.py` -> `ai/tools_schema.py` - LLM-facing schema for all of the above
- `core/assistant.py` - `self.mission_manager` initialized at startup;
  `self.mission_startup_brief` computed once (best-effort, matches the
  self_healing/learning_engine/ultron_shield init pattern above it)
- `main.py` - prints `runtime.mission_startup_brief` right after the
  runtime is created, if there is one

## Relationship to intelligence/goal_manager/
A Goal (goal_manager) is one actionable objective inside a session. A
Mission is the higher-level thing that spans many goals/sessions/days.
`mission_manager.link_goal(mission_id, goal_id)` ties the two together
without either package needing to know the other's internals.

## Not yet done (left for later passes)
- No LLM-side prompt instructing the model to actually call
  `create_mission` when a user states a multi-day objective, or to
  call `get_resumable_mission` at conversation start - the tools exist
  and are wired, but nothing currently decides *when* to use them
  automatically. Wire this into `ai/prompts/system_prompts.py` or
  `ai/prompts/ultron_proactive.py` next.
- No UI surface (web_dashboard / orb) shows active missions yet.
