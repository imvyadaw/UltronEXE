# Tool Benchmark (P4 - Automatic Tool Benchmarking & Reliability Scoring)

## What it does
Real per-call latency percentiles (p50/p95) and success-rate trend
detection (degrading/stable/improving) per tool, computed from raw
call samples in `database/tool_benchmark.db`.

## Files
- `benchmark_store.py` - sqlite CRUD for per-call samples (`benchmark_calls`)
- `tool_benchmark_engine.py` - percentiles + trend + degrading-tools report

## Wired into
- `core/executor.py` - `_get("tool_benchmark_engine")` singleton + tool_map entries:
  `record_tool_benchmark`, `get_tool_benchmark`, `get_tool_benchmark_report`, `get_degrading_tools`
- `ai/p4_engine_tools.py` -> `ai/tools_schema.py` - LLM-facing schema for all of the above

## Relationship to existing modules
Complements `ai/tool_chain_optimizer.py` (P1), which keeps a single
cumulative Bayesian success score per tool for "which tool to pick".
This module answers a different question - real latency and whether
a tool's performance is trending worse over time - from raw timing
samples the optimizer doesn't keep.

## Not yet done
- `record()` isn't yet called automatically from
  `core/action_pipeline.py` stage 5 alongside `tool_chain_optimizer`'s
  own stat recording - wire that in next so benchmarks build up
  without manual `record_tool_benchmark` calls.
- No automatic alert/health-check hook for `get_degrading_tools()`
  results yet.
