"""
Phase 16 bridge
===============
Single entry point Phase 17 code reaches through instead of importing
core.brain / core.events / plugins.manager / config.py directly one by
one. Everything here is lazy (nothing touches Groq, the plugin loader,
or the filesystem until first accessed) and read-only with respect to
Phase 16 - this file starts nothing that wasn't already going to start,
it just gathers the existing singletons behind one object so a Phase
17 module has one import instead of five, and so Phase 16's internal
wiring can keep changing without every Phase 17 caller needing to know.

    from core_integration.phase16_bridge import get_bridge
    bridge = get_bridge()
    bridge.brain.chat("hello")
    bridge.events.emit("phase17:ready")
    bridge.plugins                      # -> List[AdaptedPlugin], loaded on demand
    bridge.config.get("ai.model_name")  # -> merged config.py + config/*.yaml value
"""

from threading import Lock
from typing import Any, List, Optional

from core.brain import get_brain

from core_integration.unified_event_bus import UnifiedEventBus, get_unified_bus
from core_integration.plugin_adapter import AdaptedPlugin, discover_adapted_plugins
from core_integration.config_migrator import get_migrated_config, get_value
from core_integration.backward_compat import check_phase16_surface

_bridge: Optional["Phase16Bridge"] = None
_lock = Lock()


class _ConfigView:
    """Thin read accessor over config_migrator's merged snapshot -
    bridge.config.get("ai.model_name") instead of a bare dict."""

    def get(self, dotted_key: str, default: Any = None) -> Any:
        return get_value(dotted_key, default)

    def snapshot(self, refresh: bool = False) -> dict:
        return get_migrated_config(refresh=refresh)


class Phase16Bridge:
    """Do not construct directly - use get_bridge()."""

    def __init__(self):
        self._plugins: Optional[List[AdaptedPlugin]] = None
        self._plugins_loaded = False
        self.config = _ConfigView()

    @property
    def brain(self):
        """core.brain.get_brain() - the AIRouter. Same object every
        Phase 16 caller (main.py, agents/) gets - not a copy."""
        return get_brain()

    @property
    def events(self) -> UnifiedEventBus:
        """The unified bus (wraps core.events' singleton - see
        unified_event_bus.py). Use this for new subscriptions; the raw
        legacy bus is still reachable at .events.legacy_bus if needed."""
        return get_unified_bus()

    @property
    def plugins(self) -> List[AdaptedPlugin]:
        """Discovers (but does not load/register) every installed
        plugin, adapted for the Phase 17 lifecycle. Cached after first
        access - call reload_plugins() to re-scan plugins/installed/."""
        if self._plugins is None:
            self._plugins = discover_adapted_plugins()
        return self._plugins

    def reload_plugins(self) -> List[AdaptedPlugin]:
        self._plugins = discover_adapted_plugins()
        return self._plugins

    def load_all_plugins(self) -> List[AdaptedPlugin]:
        """Loads every discovered plugin via AdaptedPlugin.load(brain) -
        the Phase 17 equivalent of plugins.manager.PluginManager.load_all(),
        with the extra on_event() wiring adapt gives old plugins for free."""
        brain = self.brain
        for adapted in self.plugins:
            if not adapted.is_loaded:
                adapted.load(brain)
        self._plugins_loaded = True
        return self.plugins

    def unload_all_plugins(self) -> None:
        for adapted in self.plugins:
            if adapted.is_loaded:
                adapted.unload()
        self._plugins_loaded = False

    def health_check(self) -> dict:
        """Cheap sanity check for Phase 17 startup: confirms the Phase
        16 surface this bridge depends on is intact (see
        backward_compat.check_phase16_surface) and that the config
        snapshot builds without error. Never raises."""
        surface = check_phase16_surface()
        try:
            self.config.snapshot()
            config_ok = True
        except Exception:
            config_ok = False
        return {
            "phase16_surface": surface,
            "phase16_surface_ok": all(surface.values()),
            "config_migrator_ok": config_ok,
            "plugin_count": len(self.plugins),
        }


def get_bridge() -> Phase16Bridge:
    """Process-wide singleton, same pattern as core.brain.get_brain()
    and core.events.get_event_bus()."""
    global _bridge
    with _lock:
        if _bridge is None:
            _bridge = Phase16Bridge()
        return _bridge
