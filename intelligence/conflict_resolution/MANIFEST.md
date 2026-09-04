# Conflict Resolution Engine (P4)

## What it does
Detects and (auto- or manually) resolves contradictions between two
sources' claims about the same subject - persisted in
`database/conflict_resolution.db`. Auto-resolution only picks a
winner when `intelligence/evidence_ledger/`'s per-source reliability
scores show a clear gap (>= 0.15) and both sources have enough judged
history; otherwise the conflict stays open for manual review.

## Files
- `conflict_store.py` - sqlite CRUD for logged conflicts (`conflicts`)
- `conflict_resolver.py` - detect / auto_resolve / manual_resolve / reports

## Wired into
- `core/executor.py` - `_get("conflict_resolver")` singleton + tool_map entries:
  `detect_source_conflict`, `auto_resolve_conflict`, `manual_resolve_conflict`,
  `list_open_conflicts`, `get_conflict_report`
- `ai/p4_engine_tools.py` -> `ai/tools_schema.py` - LLM-facing schema for all of the above

## Relationship to existing modules
Nothing else in the build currently notices cross-source
disagreement. Best-effort reads `intelligence/evidence_ledger/`'s
`get_source_reliability()` (P2) to auto-resolve; leaves both
`evidence_ledger` and `intelligence/knowledge_os/` (P3) unmodified.

## Not yet done
- `intelligence/knowledge_os/`'s `remember_fact()` `conflicting_with`
  field isn't yet auto-forwarded into `detect_source_conflict` - a
  caller currently has to notice it and call this explicitly.
