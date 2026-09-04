# Autonomy + Multi-agent swarm upgrade

## What changed

New file: `multi_agent_swarm/dependency_planner.py` (`DependencyAwarePlanner`).
Modified: `multi_agent_swarm/agent_orchestrator.py` — `handle_request()` now
takes an LLM-planned dependency graph and dispatches it as a DAG
(`_dispatch_dag`, `_inject_dependency_context`, `_dispatch_with_retry`,
new). `handle_request(use_dependency_planning=False)` preserves the exact
old flat-dispatch behavior for any caller that depends on it.
`run_swarm_review()` and every `specialist_agents/*.py` file are untouched.

## Why (a confirmed, concrete bug — not a hypothetical)

`multi_agent_swarm/MANIFEST.md`'s own usage example is:

> "Research the top 3 Python web frameworks, then write a short summary
> comparing them"

Traced end to end, this couldn't actually work correctly:

1. `task_delegation.py`'s `decompose()` is a **regex split** on
   "then"/";"/". " — it has no concept of one subtask needing another's
   *output*, only independent pieces of text.
2. `agent_orchestrator.handle_request()` dispatches subtasks with no unmet
   dependency **in parallel by default** — so the "research" and "write"
   halves would run at the same time.
3. `specialist_agents/writer_agent.py`'s `_run()` reads `task["description"]`
   as the content to write about. After the split, that's just "write a
   short summary comparing them" — there is no field anywhere carrying
   research_agent's actual findings into the writer's task.

Net effect: the writer specialist has no way to know what "them" refers
to. Verified directly (see benchmark below) — the old path's writer output
is `"Summary of [UNSPECIFIED - no subject was provided in this task]"`.

## What the new code does about it

1. **`DependencyAwarePlanner.plan()`** — asks the LLM (via `ai_router`, same
   as every other reasoning call in the project) to decompose a request into
   subtasks *and* say which earlier subtasks each one needs the output of.
   Dependencies are restricted to strictly-earlier indices at parse time
   (so a cycle is structurally impossible), and any malformed/unparseable
   LLM response falls back to `task_delegation.py`'s existing offline split
   with all subtasks independent — i.e. degrades to *exactly* today's
   behavior, never to something worse.
2. **`AgentSwarmOrchestrator._dispatch_dag()`** — runs subtasks in
   topological batches: everything with no unmet dependency runs together
   (still concurrent, still bounded by `MAX_PARALLEL_AGENTS`), then the
   next batch, and so on.
3. **`_inject_dependency_context()`** — right before a dependent subtask
   runs, its dependencies' actual results get folded into its
   `description` field — the one field every existing specialist already
   reads. No specialist file needed to change.
4. **`_dispatch_with_retry()`** — this is the "autonomy" half: each
   dispatched subtask now gets one bounded self-critique + retry pass,
   reusing `cognitive_core/self_critique_agent.py` (same fail-closed,
   never-raises pattern `autonomous_executor.py` already uses for whole
   goals) — applied here to a single swarm subtask instead of a whole
   autonomous goal. If critique isn't importable, this no-ops back to a
   plain dispatch — additive, not a hard dependency.

## Benchmark

`tests/benchmark_swarm_dependency_planning.py` — no live LLM/API key in
this sandbox (`groq` isn't even installed here), so `_dispatch()` is
monkeypatched to a stub specialist for both paths and
`DependencyAwarePlanner` is exercised against a stub router — same
technique as the reasoning-engine benchmark. Result on the MANIFEST's own
example request:

| Path | Writer subtask's `depends_on` | Writer output grounded in research? |
|---|---|---|
| OLD (`use_dependency_planning=False`) | `[]` | **No** — `"Summary of [UNSPECIFIED ...]"` |
| NEW (dependency-aware DAG) | `[0]` | **Yes** — summary actually built from the research finding |

`tests/benchmark_deliberative_reasoning.py`'s stub-router technique was
reused for `dependency_planner.py`'s own fallback paths too — verified
separately: unparseable LLM output and a malformed subtask entry both
degrade cleanly to the old offline split.

Full codebase still compiles clean: 1358/1358 files, 0 regressions (1355
baseline + this session's earlier `deliberative_reasoning.py` +
`dependency_planner.py` + this benchmark file).

## Not done (be aware)

- No real-LLM run — needs a `GROQ_API_KEY` (or local Ollama) on your own
  machine for real decomposition-quality numbers; `groq` isn't installed
  in this sandbox at all, so `specialist_agents/writer_agent.py`,
  `code_agent.py`, etc. couldn't be exercised for real here either.
- `run_swarm_review()` (same-question-to-many-agents path) doesn't use
  dependency planning — it's a different shape (one question, many answers,
  consensus) where the concept doesn't apply the same way, so it's
  untouched on purpose.
- `_dispatch_with_retry()`'s critique call re-judges the *whole* subtask
  description against the result each time; it doesn't yet feed the
  cross-subtask context (from `_inject_dependency_context`) into what
  "satisfied" means beyond what's already folded into the description —
  fine for now since the description *is* where that context lives, but
  worth knowing if you extend this further.
- `deliberative_reasoning.py`'s new `confidence` field (from the last
  session) still isn't wired into either `decision_engine.py` or this
  swarm's critique/retry loop — two now-separate confidence signals
  (reasoning-confidence, subtask-critique) that could reasonably be
  unified later.
