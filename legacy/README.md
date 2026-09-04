# Legacy / Orphaned Code

This folder holds a second, disconnected "Ultron" implementation that
was found during a codebase audit (Sept 2026). It was not deleted -
only moved here - in case anything in it is still wanted later.

## What's here and why

- `main_ultron.py` - an alternate CLI entrypoint, separate from the
  real one (`main.py`).
- `ULTRON_CORE/` - a small module tree (`consciousness/free_will.py`,
  `consciousness/self_awareness.py`, `autonomy/resource_optimizer.py`)
  that only `orchestration/` and `activation/` depended on.
- `orchestration/` - goal manager, planner, executor, recovery
  manager for the `main_ultron.py` flow.
- `activation/` - boot/health-check/shutdown sequence for the same
  flow.
- `proactive/initiative_engine.py` and
  `environment/resource_manager.py` - the only two files in the
  active tree that imported from `ULTRON_CORE`; nothing else
  referenced them either, so they came along.
- `tests/test_core.py`, `tests/test_orchestration.py` - tests that
  only covered this code.

## Why it moved

At audit time, everything above was reachable only from itself and
`main_ultron.py` - nothing in the real, running system (`main.py` ->
`core/` -> `ai/` -> `intelligence/` ...) called into it. Two
entrypoints with two unrelated architectures in one project was
confusing and added dead weight. `main.py` is the one actively
developed and wired to every feature upgrade (wellness, finance,
etc.), so it stays canonical.

## Verified before moving

A full static import-resolution pass over the remaining active
codebase (1350 files) after this move found **0 broken imports** -
nothing outside this folder depended on any of it.

## Second pass - unused/superseded modules (43 files)

A follow-up scan checked every remaining active file for references -
static imports AND string-based ones (config files, YAML, JSON,
dynamic `importlib`/`pkgutil` registries like `skills/skill_executor.py`
and `tools/registry.py`). 52 files had zero static references; 9 of
those turned out to be loaded dynamically (kept in place). The other
**43 were confirmed genuinely unused** - each one's functionality is
covered by a different, actively-wired module:

- `voice/voice_engine.py`, `voice/speech_input.py`,
  `voice/speech_output.py` - real voice path is
  `voice/voice_commands.py` + `voice_intelligence/`.
- `security/access_controller.py`, `permission_engine.py`,
  `risk_engine.py`, `threat_monitor.py` - active security path uses
  other specific modules (e.g. `security/encryption.py`).
- `memory/memory_manager.py` - active memory path is `core/memory.py`
  + `advanced_memory/`.
- Plus 37 more across `agents/`, `environment/`, `proactive/`,
  `simulation/`, `tool_creation/`, `quantum_dashboard/`,
  `integration/`, `knowledge/`, `ultron_shield/`, `cross_device/`,
  `skill_creator/`, `hardening/`, `learning/`, `tools/`, and
  `self_evolution/` - each individually verified to have no caller
  anywhere in the active tree.

Verified after this move too: 1305 active files, 0 syntax errors,
0 broken imports.

## If you want this back

Everything here is untouched, just relocated. Move a piece back to
its original path (see paths above) and it should work as before -
just note it still won't be wired into `main.py`'s tool/agent system
unless someone does that integration work.
