"""
Plugin adapter
==============
plugins/sdk/base.py's UltronPlugin has exactly one method: register(brain).
That's everything plugins/manager.py + plugins/loader/loader.py need, and
plugins/installed/telegram/ (the one shipped plugin) only needs that too -
so it is NOT being changed.

Phase 17 plugins want more than that (an unload/teardown hook, and the
ability to react to the unified event bus instead of only being handed
`brain` once at load time). Rather than widen UltronPlugin - which would
force plugins/installed/telegram/plugin.py to be rewritten - this file
adapts each *old* plugin instance to the *new*, richer shape, so old and
new plugins can be driven by one Phase 17 loop uniformly.

Nothing here touches plugins/loader/loader.py or plugins/manager.py -
discover_plugins() and PluginManager.load_all() still work exactly as
before for anything that just wants Phase 16 behavior.
"""

from typing import Callable, List, Optional

from plugins.loader.loader import discover_plugins
from plugins.sdk.base import UltronPlugin

from core_integration.unified_event_bus import get_unified_bus


class AdaptedPlugin:
    """Wraps one legacy UltronPlugin instance with the Phase 17 lifecycle:
    load(brain) -> [plugin reacts to unified bus events, if it wants to] -> unload().

    A legacy plugin opts into the extra hooks simply by defining them -
    none are required:
        on_event(event_name: str, **payload)  - called for every event on
                                                  the unified bus once loaded
        unload()                              - called on teardown

    Plugins that define neither (every plugin today) behave exactly as
    they did under plugins/manager.py - load() calls register(brain) and
    that's it.
    """

    def __init__(self, legacy_plugin: UltronPlugin):
        self._plugin = legacy_plugin
        self._loaded = False
        self._unsubscribe: Optional[Callable[[], None]] = None

    @property
    def name(self) -> str:
        return getattr(self._plugin, "name", "unnamed-plugin")

    @property
    def legacy_plugin(self) -> UltronPlugin:
        return self._plugin

    def load(self, brain) -> bool:
        """Calls the plugin's existing register(brain) unchanged, then
        wires on_event() to the unified bus if the plugin defines one.
        Returns False (never raises) on failure, same best-effort
        philosophy as plugins/manager.py's load_all()."""
        try:
            self._plugin.register(brain)
        except Exception as e:
            print(f"[plugin_adapter] Failed to load '{self.name}': {e}")
            return False

        on_event = getattr(self._plugin, "on_event", None)
        if callable(on_event):
            bus = get_unified_bus()
            self._unsubscribe = bus.subscribe("*", lambda event_name, **payload: on_event(event_name, **payload))

        self._loaded = True
        return True

    def unload(self) -> None:
        """Best-effort teardown: unsubscribes from the bus, then calls
        the plugin's own unload() if it has one. Safe to call on a
        plugin that was never loaded or has no unload()."""
        if self._unsubscribe is not None:
            try:
                self._unsubscribe()
            except Exception:
                from core.error_trace import log_swallowed as _lsw

                _lsw("core_integration.plugin_adapter.unload")
            self._unsubscribe = None

        teardown = getattr(self._plugin, "unload", None)
        if callable(teardown):
            try:
                teardown()
            except Exception as e:
                print(f"[plugin_adapter] '{self.name}' raised during unload(): {e}")

        self._loaded = False

    @property
    def is_loaded(self) -> bool:
        return self._loaded


def adapt_plugin(legacy_plugin: UltronPlugin) -> AdaptedPlugin:
    return AdaptedPlugin(legacy_plugin)


def discover_adapted_plugins() -> List[AdaptedPlugin]:
    """Same discovery plugins/loader/loader.py already does
    (plugins/installed/*/plugin.py -> PLUGIN instance), each wrapped for
    the Phase 17 lifecycle. Does not load/register anything by itself -
    mirrors discover_plugins() only returning instances, not running them."""
    return [adapt_plugin(p) for p in discover_plugins()]
