"""system_control.system_config
================================
Windows system-configuration control surface: registry (read/write +
backup/restore), environment variables, system properties/info, device
manager, Windows Update, System Restore, and BIOS/UEFI info - the
"deep OS control" layer that sits above windows/registry,
windows/system_info, apps/system/device_manager (GUI-launch focused) etc.

Every class here follows the same conventions used throughout windows/*:
  - HAS_<DEP> guards so importing on non-Windows / without an optional
    dependency never crashes, just disables that class's methods with a
    clear {"error": ...} dict.
  - Every public method returns a plain Dict - never raises - so the AI
    tool-calling loop (ai/system_config_tools.py) never has to wrap
    calls in try/except.
  - Anything that changes system state (write/delete/enable/disable/
    install) is confirm-gated: first call with confirm=False (default)
    returns a description of what WOULD happen; the caller must repeat
    the call with confirm=True to actually do it. This mirrors
    windows/registry/editor.py's delete_value/delete_key pattern and
    approval/approval_rules.py's high-risk-tools model.
  - HKLM/system-wide writes need admin and are blocked outright (not
    just confirm-gated) unless explicitly documented otherwise, same
    safety line windows/registry/editor.py already draws for HKCU-only.

Lazily imported by ai/system_config_tools.py - importing this package
itself does no I/O.
"""

from system_control.system_config.registry_manager import RegistryManager
from system_control.system_config.registry_backup import RegistryBackup
from system_control.system_config.environment_variables import EnvironmentVariables
from system_control.system_config.system_properties import SystemProperties
from system_control.system_config.device_manager import DeviceManagerControl
from system_control.system_config.windows_update import WindowsUpdate
from system_control.system_config.system_restore import SystemRestore
from system_control.system_config.bios_uefi import BiosUefi

__all__ = [
    "RegistryManager",
    "RegistryBackup",
    "EnvironmentVariables",
    "SystemProperties",
    "DeviceManagerControl",
    "WindowsUpdate",
    "SystemRestore",
    "BiosUefi",
]
