# CORE_INTEGRATION

The bridge between the Phase 1-16 runtime and Phase 17. Every file here
wraps something that already exists - nothing in `core/`, `plugins/`,
`config.py`, or `config/*.yaml` was modified to build this.

| File | Wraps | Adds |
|---|---|---|
| `unified_event_bus.py` | `core.events.EventBus` (the one singleton) | wildcard/namespaced subscriptions, capped history + `replay()`, `subscribe()` returns an unsubscribe callable |
| `plugin_adapter.py` | `plugins.sdk.base.UltronPlugin` + `plugins.loader.loader.discover_plugins()` | optional `on_event()`/`unload()` lifecycle hooks for plugins that define them; plugins that don't behave exactly as before |
| `config_migrator.py` | `config.py` + `config/default.yaml` + `config/{APP_ENV}.yaml` | one merged, versioned JSON snapshot at `storage/config/migrated_config.json`; idempotent; timestamped backups on change; secrets deliberately excluded |
| `backward_compat.py` | nothing yet | a `shim()` registry + `check_phase16_surface()` startup check, ready for the first real Phase 17.2 rename |
| `phase16_bridge.py` | all of the above + `core.brain.get_brain()` | single `get_bridge()` facade so Phase 17 code needs one import, not five |

## Usage

```python
from PHASE_17_1_FOUNDATION.CORE_INTEGRATION.phase16_bridge import get_bridge

bridge = get_bridge()
bridge.brain.chat_with_tools(...)          # same AIRouter every Phase 16 caller gets
bridge.events.emit("phase17:ready")        # forwards to the real core.events bus too
bridge.plugins                             # -> List[AdaptedPlugin]
bridge.load_all_plugins()
bridge.config.get("ai.model_name")
bridge.health_check()                      # sanity check at Phase 17 startup
```

## Guarantees

- **Nothing is imported by Phase 16.** `main.py`, `core/`, `plugins/`,
  `ui/` have zero references to `PHASE_17_1_FOUNDATION/` - it is purely
  additive and safe to delete.
- **Only one bus, one brain, one plugin registry exist.** Everything
  above wraps the Phase 16 singleton, it never constructs a second one.
- **No file writes outside `storage/config/`.** `config_migrator.py` is
  the only file that touches disk, and only under `storage/config/`
  (snapshot + `backups/`), matching the existing `storage.*` layout in
  `config/default.yaml`.

## Verifying

```bash
python3 -c "
from PHASE_17_1_FOUNDATION.CORE_INTEGRATION.phase16_bridge import get_bridge
b = get_bridge()
print(b.health_check())
"
```
