# Phase 29-A - Stability layer

Sits underneath `PHASE_29_INTEGRATION` (which answers *"is this build GO to
ship"*) and closes gaps that show up one layer lower - before a pipeline
test even gets to run.

| Module | What it does |
|---|---|
| `lazy_loader.py` | Defer a heavy/optional third-party import (groq, ultralytics/torch, ...) to first use instead of module-load time. |
| `dependency_validator.py` | Cheap (non-importing) report of what's actually installed - required vs. optional, and which optional feature each missing package affects. |
| `exception_hardening.py` | Import one component in isolation; a broken/missing one doesn't take a whole composing module (like `windows/__init__.py`) down with it. |
| `resource_cleanup.py` | One process-wide registry for shutdown cleanup (DB connections, browser sessions, watchers, ...) instead of each module being on its own. |
| `truth_prompt_contract.py` | System-prompt addendum + a runtime heuristic check that a response's claims match what tools actually reported this turn. |
| `run_phase29a.py` | VALIDATION CLI: compile / unit / integration / dependency checks, same GO/NO-GO convention as `PHASE_29_INTEGRATION/run_phase29.py`. |

## Why this phase exists

`PHASE_29_INTEGRATION`'s own README flagged a real, live bug as a "known
environment note" rather than fixing it: `core/executor.py` imports
`windows/`, and `windows/__init__.py` imports `agents/coding_agent.py`
(`from groq import Groq`) and `vision/object_detection/yolo_detector.py`
(`from ultralytics import YOLO`, which itself imports `torch`) **at module
level**. Importing `windows` - done unconditionally by `core/executor.py`
for every single tool call, whether it touches coding/vision or not - used
to always pay Groq's and torch's import cost, and would have hard-failed
with `ModuleNotFoundError` in any environment missing either package.

Phase 29-A fixes that at the two concrete call sites (`agents/coding_agent.py`,
`vision/object_detection/yolo_detector.py`, both now using
`lazy_loader.lazy_attr`/`lazy_module`) and adds the general-purpose tools
(`lazy_loader`, `exception_hardening`) so the same pattern doesn't
regress elsewhere, plus three more pieces the "existing services" pass
turned up:

- **Resource cleanup** had no single owner - each module was responsible
  for its own, with no guarantee anything actually ran it on shutdown.
- **Notifications** (`ui/notifications.py`) and **UsageTracker**
  (`storage/cache/usage_tracker.py`) were audited against Phase 29-A's
  checklist and found already sound (both are themselves prior-phase
  fixes, per their own docstrings) - no changes needed there.
- **Truth prompt contract** didn't exist at all: `SYSTEM_PROMPT` documents
  *when* to call a tool in detail but said nothing about what to do with
  the result once it comes back. Added as a new system-prompt section
  (`TRUTH_CONTRACT_ADDENDUM`, wired into `ai/prompts/system_prompts.py`'s
  `SYSTEM_PROMPT`) plus a non-blocking runtime check (`check_turn()`) that
  flags - for logging, not censorship - a response claiming an action
  succeeded with no matching successful tool call, or a tool error the
  response text doesn't reflect. Wired into `ai/cloud_models/groq_client.py`'s
  `chat_with_tools()` (the actual tool-calling loop, both the native and
  legacy-text-fallback paths) so it runs on every real turn, not just where
  it's called explicitly - failures in the check itself are swallowed so it
  can never be the reason a real response fails to return.

## Usage

```bash
# from the Ultron/ directory
python -m PHASE_29_A_STABILITY.run_phase29a                # all four checks
python -m PHASE_29_A_STABILITY.run_phase29a --compile       # compile only
python -m PHASE_29_A_STABILITY.run_phase29a --unit          # unit tests only
python -m PHASE_29_A_STABILITY.run_phase29a --integration   # imports windows + runs Phase 29's pipeline test
python -m PHASE_29_A_STABILITY.run_phase29a --dependency    # dependency report only
```

Exit code `0` on PASS, `1` on FAIL - same convention as
`core/startup.py` and `PHASE_29_INTEGRATION/run_phase29.py`.

```python
from PHASE_29_A_STABILITY import lazy_attr, register_cleanup, safe_import_component

get_Groq = lazy_attr("groq", "Groq")          # import only happens on first call
handle = register_cleanup("my_driver", driver.quit)   # runs on shutdown, or handle.run_now()
Thing = safe_import_component("some.module", "Thing")  # None + logged, instead of crashing the caller
```

## Tests

```bash
pytest PHASE_29_A_STABILITY/tests/ -v
```

Dependency-free (no groq/ultralytics/torch required), same "fake stages,
not the full dependency stack" approach as
`PHASE_29_INTEGRATION/tests/test_phase29_integration.py`. Real-codebase
wiring (does `windows` actually import, does the rest of the app still
work with this phase's changes in place) is exercised by
`run_phase29a.py --integration`, which is what CI/pre-deploy should run.

## Verified in this build

- `import windows` succeeds with `groq` installed but `ultralytics`/`torch`
  **not** installed (previously this combination worked only because the
  ultralytics import was already inside a `try/except`; the *groq* import
  in `agents/coding_agent.py` was not, and would have raised).
- `import agents.coding_agent` no longer imports `groq` at all until a
  `CodingAgent()` is actually constructed with a `GROQ_API_KEY` set.
- `PHASE_29_A_STABILITY.run_phase29a` (all four checks) and
  `PHASE_29_INTEGRATION.run_phase29` (deploy check) both pass in this
  environment.
- The existing `testing/unit/test_notifications.py`,
  `PHASE_29_INTEGRATION/tests/`, and `agents/` test suites still pass
  unchanged.
