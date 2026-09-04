# COGNITIVE_CORE

A bounded "goal → plan → execute → critique → replan" loop for requests
too open-ended for a single tool call (`core/executor.py`) or a fixed
workflow (`core/workflow_engine.py`). Composes existing Phase 1-16
machinery - nothing here re-implements tool dispatch, retries, or
schema validation.

| File | Wraps | Adds |
|---|---|---|
| `context_bridge.py` | `core.context.ConversationContext` (never previously instantiated), `core.memory.MemoryStore`, Phase 17.1's `get_bridge()` | one snapshot/observability surface; emits `cognition:*` on the unified event bus |
| `goal_planner.py` | `ai.planning.Planner` (unchanged, used for the quick path) | an extra LLM pass that breaks a goal into human-readable sub-goals, replan-with-feedback support |
| `task_decomposer.py` | `ai.planning.Planner.make_plan()` per sub-goal | flattens multi-sub-goal plans into one `core.workflow_engine`-ready step list, with `subgoal_index` tagging and optional `run_if` chaining |
| `self_critique_agent.py` | nothing (new capability) | one LLM pass judging "was the goal actually achieved", with a structural fallback (`all steps succeeded`) if the LLM call fails |
| `autonomous_executor.py` | `core.workflow_engine.run_ad_hoc()`, `core.error_handler` (via workflow_engine) | the loop itself, bounded by `MAX_SUBGOAL_ATTEMPTS` (2) and `MAX_TOTAL_STEPS` (40) - it always stops, never silently keeps retrying |
| `intent_resolver.py` | `core.intent_router.classify()`/`.route()` (unchanged, always wins first) | one new `GOAL` intent for `"goal: ..."` / `"handle X end to end"` / Hinglish equivalents, otherwise a pure passthrough |

## Usage

```python
from PHASE_17_2_COGNITIVE_BRAIN.COGNITIVE_CORE.intent_resolver import route

# drop-in replacement for core.intent_router.route() - everything it
# already handled (workflow/background/task_status/list_tasks/chat)
# behaves identically; only newly-classified GOAL requests are new.
result = route("goal: clean up my Downloads and email me a summary")
print(result.response)   # "Working on '...' autonomously (task <id>)..."
```

```python
from PHASE_17_2_COGNITIVE_BRAIN.COGNITIVE_CORE.autonomous_executor import get_autonomous_executor

outcome = get_autonomous_executor().run_goal("organize my Downloads folder", quick=False)
outcome["satisfied"]          # bool - self_critique_agent's final call
outcome["subgoal_results"]    # per-sub-goal attempts, reports, critiques
outcome["stopped_reason"]     # None, or "step_ceiling_reached"
```

## Safety properties

- **Bounded, always.** `MAX_TOTAL_STEPS` is a hard ceiling checked
  before every sub-goal and mid-decomposition - a bad plan can spawn at
  most 40 tool calls per goal, never more, and the executor always
  returns cleanly with `stopped_reason` set rather than hanging.
- **No new tool capability.** Every tool call still goes through
  `core.executor.execute_tool` via `core.workflow_engine.run_ad_hoc()` -
  the cognitive layer decides *when* to call things, never gains access
  to anything the existing tool schema didn't already expose.
- **Fails closed toward the old behavior.** `core.intent_router`'s
  existing intents always win in `intent_resolver.classify()`;
  `self_critique_agent` degrades to a plain structural check if the LLM
  call errors; `goal_planner` degrades to a single sub-goal (the
  original goal, unchanged) if sub-goal breakdown returns unparseable
  JSON. Nothing here ever raises out to the caller.
- **Purely additive.** Nothing in `core/`, `ai/`, `agents/`, or
  `main.py` imports anything from `PHASE_17_2_COGNITIVE_BRAIN/` - same
  guarantee as `PHASE_17_1_FOUNDATION/CORE_INTEGRATION`.

## Verifying

```bash
python3 -c "
from PHASE_17_2_COGNITIVE_BRAIN.COGNITIVE_CORE.intent_resolver import classify
r = classify('goal: back up my documents folder')
print(r.intent, r.payload)
"
```
