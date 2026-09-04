# Resource-Aware Intelligence Engine (P3)

## What it does
Recommends how a task should actually be executed - full local run,
lighter local path, deferred, or cloud-offloaded - based on current
system load (`monitoring/resource_monitor.py` best-effort, falls back
to raw psutil, falls open if neither available) plus that task type's
own empirical cost history in `database/resource_intelligence.db`.

## Files
- `resource_store.py` - sqlite CRUD for per-task-type cost history (`task_costs`)
- `resource_aware_engine.py` - load + history -> execution tier recommendation

## Wired into
- `core/executor.py` - `_get("resource_aware_engine")` singleton + tool_map entries:
  `recommend_execution_tier`, `track_task_resource_cost`, `get_resource_intelligence_report`
- `ai/p3_engine_tools.py` -> `ai/tools_schema.py` - LLM-facing schema for all of the above

## Relationship to existing modules
Complements, does not replace:
`monitoring/resource_monitor.py` (raw snapshots) and
`intelligence/predictive_preparation/resource_optimizer.py` (in-memory
cooldown gate for *background* preloading only). This engine is for
task execution routing, not background preloading, and persists its
cost history across restarts.

## Not yet done
- Nothing currently calls `track_task_resource_cost` automatically
  after a real tool/task runs - wire into `core/action_pipeline.py`
  next so profiles build up without manual logging.
