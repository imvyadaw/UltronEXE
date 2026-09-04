# P1 Integration Notes

Implements and wires the 3 items you marked P1. Verified with
`python3 -m py_compile` on every touched/new file plus a standalone
functional smoke test of all three engines (mission create/checkpoint/
resume, tool ranking, capability isolation deny/ask/allow) - all
passed. Not run inside the full app (needs your API keys / OS-specific
deps), so test it end-to-end in your own environment before relying on
it.

## 1. Mission Persistence Engine
New: `intelligence/mission_engine/` (`mission_store.py`, `mission_manager.py`)
See `intelligence/mission_engine/MANIFEST.md` for full detail.
- Survives restarts via `database/missions.db`
- Auto-resume: `main.py` prints a "you still have an open mission" line
  on boot if one's been idle 5+ minutes
- New tools: `create_mission`, `checkpoint_mission`, `list_active_missions`,
  `get_resumable_mission`, `resume_mission`, `pause_mission`,
  `complete_mission`, `abandon_mission`

## 2. Intelligent Tool-Chain Optimizer
New: `ai/tool_chain_optimizer.py`
- Records every action's success/failure/latency via
  `core/action_pipeline.py`'s stage 5 (record) - so it learns from
  everything already flowing through ActionPipeline, no separate
  instrumentation needed anywhere else
- Recency-weighted, Bayesian-prior scoring (0..1) - a tool that's
  started failing recently drops in score faster than an old failure
  streak would; a brand-new tool starts neutral (0.5) instead of 0
- New tools: `rank_tool_candidates`, `optimize_tool_chain`,
  `get_tool_reliability_report`

## 3. Capability Isolation / Fine-Grained Permissions
New: `security/capability_isolation.py`
- Adds a **second axis** on top of the existing
  `core/capability_registry.py` (which only has permission_level:
  normal/elevated/destructive): a *scope* per tool (filesystem_read,
  filesystem_write, network, shell_exec, system_control,
  communication_send, automation_ui, media_control, financial)
- Named isolation **profiles** (`default`, `guest`, `locked_down`,
  extensible) each set allow/ask/deny per scope, independent of
  permission_level - e.g. you can allow all "normal" actions except
  deny every `communication_send` scope regardless of risk tier
- Wired as stage "1.5 isolate" in `core/action_pipeline.py`, right
  after capability resolution and before PermissionGate - so it's a
  pure additional gate, never loosens what already existed
- Policy persists to `security/capability_policy.json` (created with
  sane defaults on first run - not included in this package)
- New tools: `check_capability_access`, `set_isolation_profile`,
  `get_isolation_policy`, `set_capability_scope_policy`

## Design principle followed throughout
Every new subsystem init is wrapped in the same
`try/except Exception: logger.exception(...)` pattern already used for
self_healing/learning_engine/ultron_shield in `core/assistant.py`, and
every hook added to `core/action_pipeline.py` is wrapped the same way.
**A checkout that's missing one of these new files still runs exactly
as it did before** - nothing here can break existing behavior, it can
only add capability on top.

## Files touched (existing files, small additive edits)
- `core/action_pipeline.py` - added isolation check + stats recording
- `core/executor.py` - added 3 singletons + 15 tool_map entries
- `ai/tools_schema.py` - appended `P1_ENGINE_TOOLS`
- `core/assistant.py` - added 3 init blocks (mission/tool-chain/isolation)
- `main.py` - prints mission startup brief if present

## Files added
- `intelligence/mission_engine/__init__.py`
- `intelligence/mission_engine/mission_store.py`
- `intelligence/mission_engine/mission_manager.py`
- `intelligence/mission_engine/MANIFEST.md`
- `ai/tool_chain_optimizer.py`
- `security/capability_isolation.py`
- `ai/p1_engine_tools.py`

## Roadmap for P3-P5 (not built yet - honest status)
P2 (Evidence Ledger + Failure Pattern Learning) is now done - see
`P2_INTEGRATION_NOTES.md`. Remaining:
  facts/concepts/relationships folders are empty scaffolding
  (`.gitkeep` only) - this is the biggest of the remaining items.
- **P3 - Resource-Aware Intelligence Engine**: no existing relative
  found (CPU/battery/network-aware throttling of what Ultron attempts).
- **P4 - Automatic Tool Benchmarking & Reliability Scoring**: P1's
  tool_chain_optimizer already gives you live reliability scoring for
  free as a side effect - what's missing is *automatic benchmarking*
  (proactively test-calling tools on a schedule rather than only
  learning from real usage). Would extend `ai/tool_chain_optimizer.py`
  rather than duplicate it.
- **P4 - Conflict Resolution Engine**: no existing relative found
  (what happens when two subsystems - e.g. a proactive suggestion and
  an active mission - want contradictory things at once).
- **P5 - Personal Workflow Graph & Automation Discovery**: `automation/`
  has macro record/playback, but nothing mines usage history into a
  graph of "you always do X after Y" to suggest new automations.

Say the word and I'll do P3 next the same way - real code, wired into
the existing conventions, not stubs.
