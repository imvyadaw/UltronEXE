"""
Plugin manager
==============
Loads every discovered plugin and calls register() on it with the shared
brain instance.
"""

from typing import List

from plugins.loader.loader import discover_plugins
from plugins.sdk.base import UltronPlugin
from core.brain import get_brain


class PluginManager:
    def __init__(self):
        self.plugins: List[UltronPlugin] = []

    def load_all(self):
        brain = get_brain()
        self.plugins = discover_plugins()
        for plugin in self.plugins:
            try:
                plugin.register(brain)
                print(f"Loaded plugin: {plugin.name}")
            except Exception as e:
                print(f"Failed to register plugin '{plugin.name}': {e}")
        return self.plugins
