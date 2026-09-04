"""
DEEP_OS_INTEGRATION
====================
System-level modules that let ULTRON observe and react to what's
happening on the machine: files, processes, network status, hardware,
clipboard, windows and the registry.

Each submodule is imported independently and set to None if its
optional dependency (pyperclip, pywin32, ...) isn't installed or its
platform doesn't apply - matching this project's existing best-effort
convention (see core/assistant.py) - so one missing package doesn't
take down process_inspector/network_monitor/filesystem_watcher, which
have no such dependency.
"""

import logging

logger = logging.getLogger("ultron.deep_os_integration")


def _optional_import(module_name: str, class_name: str):
    try:
        module = __import__(f"deep_os_integration.{module_name}", fromlist=[class_name])
        return getattr(module, class_name)
    except ImportError as e:
        logger.info("[deep_os_integration] %s unavailable (%s) - continuing without it", class_name, e)
        return None


GlobalHookManager = _optional_import("global_hook_manager", "GlobalHookManager")
FilesystemWatcher = _optional_import("filesystem_watcher", "FilesystemWatcher")
ProcessInspector = _optional_import("process_inspector", "ProcessInspector")
NetworkMonitor = _optional_import("network_monitor", "NetworkMonitor")
DriverController = _optional_import("driver_controller", "DriverController")
ClipboardIntelligence = _optional_import("clipboard_intelligence", "ClipboardIntelligence")
WindowManagerHook = _optional_import("window_manager_hook", "WindowManagerHook")
RegistryMonitor = _optional_import("registry_monitor", "RegistryMonitor")

__all__ = [
    "GlobalHookManager",
    "FilesystemWatcher",
    "ProcessInspector",
    "NetworkMonitor",
    "DriverController",
    "ClipboardIntelligence",
    "WindowManagerHook",
    "RegistryMonitor",
]
