# Knowledge OS (P3 - Unified Personal Knowledge OS)

## What it does
Single front door over Ultron's otherwise-scattered knowledge. Keeps
its own source-tagged fact ledger (`database/knowledge_os.db`) and,
on read, best-effort merges in `intelligence/knowledge_graph/` and
`memory/semantic_memory.py` so "what do you know about X" gets one
answer instead of requiring several separate lookups.

## Files
- `knowledge_store.py` - sqlite CRUD for the OS's own `facts` table
- `knowledge_os_engine.py` - unified read/search + best-effort cross-subsystem enrichment + staleness report

## Wired into
- `core/executor.py` - `_get("knowledge_os")` singleton + tool_map entries:
  `remember_fact`, `get_unified_knowledge_view`, `search_knowledge`, `get_knowledge_freshness_report`
- `ai/p3_engine_tools.py` -> `ai/tools_schema.py` - LLM-facing schema for all of the above

## Relationship to existing modules
Does not replace `intelligence/knowledge_graph/` or
`memory/semantic_memory.py` - both are untouched and queried
best-effort (a missing/erroring subsystem just contributes nothing to
the merged view, it never breaks it).

## Not yet done
- No auto-detection of when a conversational statement should become
  a `remember_fact` call - currently explicit tool calls only.
- `conflicting_with` results from `remember_fact` aren't yet
  auto-forwarded to `intelligence/conflict_resolution/` - a caller has
  to notice the field and call `detect_source_conflict` itself.
