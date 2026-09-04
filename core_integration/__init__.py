"""
CORE_INTEGRATION
================
The five seams Phase 17 needs into the existing Phase 16 runtime:

    phase16_bridge.py    - single facade onto brain/event bus/plugins/config
    unified_event_bus.py - namespaced, wildcard, history-aware bus that
                            wraps core.events.EventBus instead of replacing it
    plugin_adapter.py    - lets old UltronPlugin subclasses run under the
                            new plugin lifecycle without being rewritten
    config_migrator.py   - merges config.py + config/*.yaml into one
                            versioned snapshot, non-destructively
    backward_compat.py   - shims so anything Phase 17 renames/moves later
                            doesn't break Phase 16 import paths

Import order doesn't matter between these - each only depends on Phase 16
modules (core.*, plugins.*, config.py, utils.helpers) plus each other, never
the reverse. Phase 16 code never needs to import anything from this folder.
"""

from core_integration.phase16_bridge import get_bridge
from core_integration.unified_event_bus import get_unified_bus

__all__ = ["get_bridge", "get_unified_bus"]
