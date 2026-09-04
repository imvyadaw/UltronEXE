# Phase 29 - Integration

Final integration layer sitting on top of Phase 17-28 (core, intelligence,
database, execution, memory, etc). Where `core/startup.py` answers *"did
each subsystem come up"*, Phase 29 answers the questions you need before
shipping a build:

| Module | Question it answers |
|---|---|
| `pipeline_test.py` | Does a full turn actually flow end-to-end across every subsystem, not just each one individually? |
| `perf_optimizer.py` | Where is that flow slow, reliably (not just on one lucky/unlucky run)? |
| `error_hardening.py` | Does one subsystem repeatedly failing take the rest of a turn down with it? |
| `deploy_check.py` | Given all of the above: is this build **GO** or **NO-GO**? |

Design principle carried over from `core/startup.py` and
`core/error_handler.py`: **degrade, don't crash**. Every check catches
its own exceptions and reports `(ok, detail)` instead of raising, so a
missing optional dependency in the current environment (no `groq`
installed, no `.env`, offline) shows up as a WARN in the report, not an
abort.

## Usage

```bash
# from the Ultron/ directory
python -m PHASE_29_INTEGRATION.run_phase29            # full GO/NO-GO deploy check
python -m PHASE_29_INTEGRATION.run_phase29 --pipeline  # pipeline test only
python -m PHASE_29_INTEGRATION.run_phase29 --perf      # perf optimizer only
```

Or from code:

```python
from PHASE_29_INTEGRATION import run_deploy_check

report = run_deploy_check()
print(report.summary())
if not report.go:
    for reason in report.reasons:
        print("blocker:", reason)
```

Exit code is `0` on GO/PASS and `1` on NO-GO/FAIL (matches
`core/startup.py`'s convention) so this drops into a pre-deploy script or
CI step as `python -m PHASE_29_INTEGRATION.run_phase29 && echo shipped`.

## 1. End-to-end pipeline test (`pipeline_test.py`)

Runs one probe utterance through the real chain a turn takes:

```
text -> core.intent_router.route()
     -> intelligence.get_intelligence_core().process_turn()
     -> core.goal_manager.get_goal_manager()   (create + complete a probe goal)
     -> core.executor.execute_tool()           (get_system_info - read-only)
     -> database.get_database_manager()        (write -> read back -> cleanup)
```

Each stage is timed and isolated - one broken stage doesn't stop the rest
from being tested. This is a *smoke* test (runs in under a second), not a
replacement for `testing/unit/` and `testing/e2e/`'s pytest suites - it
exists to answer "does the whole chain still connect after this change?"
fast enough to run before every deploy.

## 2. Performance optimization (`perf_optimizer.py`)

`core/perf_trace.py` deliberately keeps only the *current* turn's T0-T7
marks in memory (see its own docstring) - it can't tell you whether a
stage is *reliably* slow. `perf_optimizer.py` runs the pipeline test N
times, keeps every stage's timing across all N runs, and reports
mean/p50/p95/max per stage plus hand-written, codebase-specific tuning
recommendations for any stage averaging above the threshold
(default 250ms). Each run's stats are also persisted into the existing
`database/intelligence/performance_metrics.db` (via `database.get_database_manager()`)
so history survives past the current process - no second metrics store
invented.

## 3. Error handling hardening (`error_hardening.py`)

Adds a per-context circuit breaker on top of `core/error_handler.py`'s
`ErrorHandler.run_safely()` (which itself is left unchanged):

- **CLOSED** - normal, every call goes through `run_safely()`.
- **OPEN** - a context has failed `failure_threshold` times in a row
  (default 5); new calls short-circuit instantly, no retry/backoff, until
  `cooldown_seconds` (default 30s) has passed.
- **HALF_OPEN** - cooldown elapsed, next call is a probe: success closes
  the circuit, failure re-opens it.

In-memory/per-process only, matching `perf_trace.py`'s stated
"single current turn, not a persisted store" scope - it protects the
current run from cascading failures; historical trend is
`perf_optimizer.py` + `deploy_check.py`'s job.

```python
from PHASE_29_INTEGRATION.error_hardening import get_hardened_handler

h = get_hardened_handler()
result = h.run_safely(some_tool_fn, arg1, arg2, context="some_tool_fn")
print(h.status())  # per-context circuit state + counters
```

## 4. Deployment readiness (`deploy_check.py`)

Combines `core.startup.run_startup_checks()`, `pipeline_test`,
`perf_optimizer`, and the current circuit-breaker status into one
`DeployReport(go: bool, reasons: list[str], ...)`. **GO** requires: no
blocking startup failure (internet being offline is a documented WARN,
not a blocker - see `core/startup.py`), the pipeline test passing, no
stage averaging above the perf threshold, and no open circuits. A single
reason is enough for NO-GO, but every reason found is listed so nothing
needs to be re-run to see the next problem.

## Tests

```bash
pytest Ultron/PHASE_29_INTEGRATION/tests/ -v
```

The self-tests exercise Phase 29's own logic (report shape, circuit
breaker transitions, threshold flagging, GO/NO-GO decision) with fake
stages rather than depending on the full Ultron dependency stack
(groq, vector DB extras, etc.) being installed - real-codebase wiring
is exercised directly by running `pipeline_test.py`/`deploy_check.py`
themselves, which is what CI/pre-deploy should actually run.

## Known environment notes (this build)

Running `deploy_check.py` surfaced two things worth knowing about,
neither of which is a Phase 29 bug:

- `core/executor.py` imports `windows/`, which imports every
  `agents/*` module at import time (`agents/coding_agent.py` needs the
  `groq` package unconditionally) even when the tool being executed
  doesn't need it. `pipeline_test.py`'s executor stage treats a
  `ModuleNotFoundError` for a known-optional package (groq, elevenlabs,
  openai, anthropic, chromadb, faiss) as a WARN rather than a FAIL, but
  the underlying import isn't lazy - worth lazily importing
  `agents/coding_agent.py` in a future phase if `windows/` needs to stay
  importable without every optional SDK installed.
- `core/startup.py`'s `config` check fails without a `.env`
  file containing `GROQ_API_KEY`. That's correct, documented behaviour,
  not something Phase 29 should silently ignore in the GO/NO-GO decision.
