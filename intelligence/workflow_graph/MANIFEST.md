# Personal Workflow Graph & Automation Discovery (P5)

## What it does
Turns already-detected repeating action patterns
(`intelligence/skill_builder/workflow_detector.py`) into a navigable
graph (`database/workflow_graph.db`) of workflow/tool nodes and
step-sequence edges, then mines it for chains that repeat often
enough to be worth suggesting as one automation.

## Files
- `workflow_graph_store.py` - sqlite CRUD for `graph_nodes` / `graph_edges`
- `workflow_graph_engine.py` - register/link/import + `discover_automation_opportunities()`

## Wired into
- `core/executor.py` - `_get("workflow_graph_engine")` singleton + tool_map entries:
  `register_workflow_graph_node`, `link_workflow_sequence`,
  `discover_automation_opportunities`, `get_workflow_graph_neighbors`,
  `get_workflow_graph_summary`
- `ai/p5_engine_tools.py` -> `ai/tools_schema.py` - LLM-facing schema for all of the above

## Relationship to existing modules
`workflow_detector.py` only answers "is this n-gram repeating" with no
structure connecting separate patterns; `core/workflow_engine.py`
executes a workflow once one exists but has no discovery step. This
engine reads `workflow_detector.get_candidates()` best-effort
(never breaks if absent) and is the missing structure + discovery
layer between the two. Neither existing module is modified.

## Not yet done
- `discover_automation_opportunities()` results aren't yet
  auto-forwarded into an actual `core/workflow_engine.py` saved
  workflow - a suggestion still requires a human (or another tool
  call) to act on it.
