"""System automations: File Explorer, Task Manager, Registry, Control Panel, Settings, PowerShell, Device Manager."""

from apps.system.file_explorer import FileExplorerApp
from apps.system.task_manager import TaskManagerApp
from apps.system.registry import RegistryApp
from apps.system.control_panel import ControlPanelApp
from apps.system.settings import SettingsApp
from apps.system.powershell import PowerShellApp
from apps.system.device_manager import DeviceManagerApp

__all__ = [
    "FileExplorerApp",
    "TaskManagerApp",
    "RegistryApp",
    "ControlPanelApp",
    "SettingsApp",
    "PowerShellApp",
    "DeviceManagerApp",
]
