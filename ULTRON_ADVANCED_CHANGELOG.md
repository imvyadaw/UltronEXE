# ULTRON Advanced Upgrade

## Added
- `intelligence/ultron_advanced/` Advanced Autonomy Fabric
- Persistent lifecycle event ledger and learned strategy scores
- World-state observation integration on conversation turns
- Mission/research/knowledge/evolution composition APIs
- Sandbox-first evolution boundary with explicit non-deployment result
- Architecture documentation

## Wired
- `core/assistant.py` initializes the Advanced Autonomy Fabric by default
- Each real conversation turn captures a fresh world-state snapshot
- Turn outcomes are recorded into the advanced learning strategy store

## Validation
- Existing test suite: 10 passed
- New Advanced Autonomy module import/status smoke test: passed

## Safety
- No new unrestricted execution path was added.
- Existing capability and permission gates remain authoritative.
- Code evolution never deploys automatically.

## Autonomous internet learning (new)
- `intelligence/ultron_advanced/autonomous_learning.py`: recurring
  scheduler that calls advanced_engine.py's previously-uncalled
  `research()` on a schedule - curated tech/general topic queue +
  knowledge_os stale-fact re-checking, one topic per cycle, results
  stored into knowledge_os.
- Gated by `ULTRON_LEARN_FROM_INTERNET` (off by default) +
  `ULTRON_LEARN_INTERVAL_HOURS` (default 6) in core/assistant.py's
  init. Manual control works regardless via new tools.
- New tools (ai/autonomous_learning_tools.py): `autolearn_status`,
  `autolearn_start`, `autolearn_stop`, `autolearn_now`,
  `autolearn_add_topic`, `autolearn_remove_topic`.
- Safety: read-only research, no destructive action, no code
  deployment. Self-halts after 3 consecutive failed cycles rather than
  retrying silently forever.

## Reactive runtime code self-patcher (new)
- `self_evolution/runtime_patcher.py`: hooks into ai/tool_runtime.py's
  two crash-catching points. Tracks repeated (tool, exception type,
  file, line) signatures; on the 2nd repeat, runs
  self_evolution/evolution_manager.py's existing sandbox
  analyze->patch->compile->test pipeline in a background thread,
  scoped to the erroring file only.
- Only copies a patch into the real project if the WHOLE sandbox run
  was accepted (compiled + tests passed). Always backs up the real
  file first (storage/self_evolution/backups/) so every auto-patch is
  instantly reversible.
- If the same exact error recurs after a patch was applied, treats it
  as a failed fix: auto-reverts from backup and permanently disables
  further auto-patch attempts for that signature (escalates to human).
- Hard-excluded from auto-patching regardless of error count:
  core/permissions.py, core/action_pipeline.py,
  core/capability_registry.py, approval/, safety/, security/,
  ultron_shield/, self_evolution/ itself - these only get logged, never
  auto-patched.
- Gated by `ULTRON_RUNTIME_SELF_PATCH_ENABLED` (off by default).
  New tool: `selfheal_code_status`.

## locate_on_screen dual-implementation fix
- Root cause: two LIVE call paths for the same tool, not dead code.
  ai/tool_runtime.py's AI tool-calling loop (_DIRECT_HANDLERS, via
  ai/perception_tools.py) already routed through
  perception/screen_analyzer.py's locate() - event-emitting, graceful
  {"available": False, ...} on failure. But core/executor.py's
  tool_map (used directly by automation/RPA/player.py,
  automation/workflow/workflow.py, automation/conditions/*.py,
  automation/triggers/*.py, voice/voice_commands.py, core/scheduler.py,
  core/planner.py, ai/local_router.py) called vision/vision_llm.py's
  locate_on_screen() raw - no perception.screen_locate event (breaks
  autonomous_engine/action_pipeline's "did this step already happen"
  tracking) and a raised exception on failure instead of a clean result.
- Fix: core/executor.py's "locate_on_screen" entry now routes through
  the same screen_analyzer.locate() as the AI loop. One implementation,
  identical behavior regardless of which caller invokes the tool.
- Verified: _get("screen_analyzer") resolves, .locate() returns the
  event-emitting wrapped shape instead of raising, in a headless
  (no-display) test environment.
