"""
Plugin loader
=============
Scans plugins/installed/*/plugin.py for a `PLUGIN` instance (a UltronPlugin
subclass) and imports it. Does not auto-run plugins - see
plugins/manager.py for that.
"""

import importlib
from pathlib import Path
from typing import List

from plugins.sdk.base import UltronPlugin


def discover_plugins() -> List[UltronPlugin]:
    installed_dir = Path(__file__).resolve().parent.parent / "installed"
    plugins: List[UltronPlugin] = []

    if not installed_dir.exists():
        return plugins

    for entry in installed_dir.iterdir():
        plugin_file = entry / "plugin.py"
        if entry.is_dir() and plugin_file.exists():
            module_name = f"plugins.installed.{entry.name}.plugin"
            try:
                module = importlib.import_module(module_name)
                plugin_instance = getattr(module, "PLUGIN", None)
                if isinstance(plugin_instance, UltronPlugin):
                    plugins.append(plugin_instance)
            except Exception as e:
                print(f"Failed to load plugin '{entry.name}': {e}")

    return plugins
