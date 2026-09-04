"""System Config tool registry
===============================
Wires system_control/system_config/* (registry manager+backup, env
vars, system properties, device manager, Windows Update, System
Restore, BIOS/UEFI) into the AI tool-calling loop. Pattern mirrors
ai/new_skills_tools.py: lazy singletons + a flat SYSTEM_CONFIG_TOOLS /
SYSTEM_CONFIG_DIRECT_HANDLERS pair, merged at the bottom of
ai/tools_schema.py and ai/tool_runtime.py respectively (see the
two-line imports there).

Naming: every tool is prefixed `sysconfig_` to avoid colliding with the
existing `registry_*` / `device_manager_*` tools in ai/apps_tools.py
(apps/system/registry.py's RegistryApp and apps/system/device_manager.py's
DeviceManagerApp - those stay focused on opening the GUI + a basic
read/list; these are the deeper programmatic control surface).

Every write/delete/enable/disable/install method on the underlying
classes is confirm-gated (confirm: bool, defaults False) - the model
should call once to preview, then again with confirm=true once the
user has agreed, same pattern as every other destructive tool in this
codebase.
"""

from typing import Dict


def _tool(name: str, description: str, properties: dict = None, required: list = None) -> dict:
    """Identical shape to ai/tools_schema.py's `_tool()` helper. Duplicated
    on purpose - see ai/new_skills_tools.py's docstring for why (avoids a
    circular import since tools_schema.py imports *from* this module)."""
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": properties or {},
                "required": required or [],
            },
        },
    }


def _pick(d: dict, keys: list) -> dict:
    """Filter a raw tool-call args dict down to the keys a method accepts,
    dropping missing/None entries so the method's own defaults apply."""
    return {k: d[k] for k in keys if k in d and d[k] is not None}


# ---------------------------------------------------------------------------
# Lazy singletons
# ---------------------------------------------------------------------------
_instances: Dict[str, object] = {}


def _get(key: str):
    if key in _instances:
        return _instances[key]

    if key == "registry_manager":
        from system_control.system_config.registry_manager import RegistryManager

        obj = RegistryManager()
    elif key == "registry_backup":
        from system_control.system_config.registry_backup import RegistryBackup

        obj = RegistryBackup()
    elif key == "env_vars":
        from system_control.system_config.environment_variables import EnvironmentVariables

        obj = EnvironmentVariables()
    elif key == "system_properties":
        from system_control.system_config.system_properties import SystemProperties

        obj = SystemProperties()
    elif key == "device_manager":
        from system_control.system_config.device_manager import DeviceManagerControl

        obj = DeviceManagerControl()
    elif key == "windows_update":
        from system_control.system_config.windows_update import WindowsUpdate

        obj = WindowsUpdate()
    elif key == "system_restore":
        from system_control.system_config.system_restore import SystemRestore

        obj = SystemRestore()
    elif key == "bios_uefi":
        from system_control.system_config.bios_uefi import BiosUefi

        obj = BiosUefi()
    else:
        raise KeyError(f"Unknown system_config tool key: {key}")

    _instances[key] = obj
    return obj


_ROOT_ENUM = ["HKCU", "HKLM", "HKCR", "HKU", "HKCC"]
_REG_TYPE_ENUM = ["REG_SZ", "REG_EXPAND_SZ", "REG_DWORD", "REG_QWORD", "REG_MULTI_SZ", "REG_BINARY"]

# ---------------------------------------------------------------------------
# Tool schemas
# ---------------------------------------------------------------------------
SYSTEM_CONFIG_TOOLS = [
    # -- RegistryManager --
    _tool(
        "sysconfig_registry_get_value",
        "Read a single Windows Registry value under any root (HKCU/HKLM/HKCR/HKU/HKCC).",
        {
            "root": {"type": "string", "enum": _ROOT_ENUM},
            "key_path": {"type": "string"},
            "value_name": {"type": "string"},
        },
        ["root", "key_path", "value_name"],
    ),
    _tool(
        "sysconfig_registry_list_values",
        "List every value under a Windows Registry key.",
        {"root": {"type": "string", "enum": _ROOT_ENUM}, "key_path": {"type": "string"}},
        ["root", "key_path"],
    ),
    _tool(
        "sysconfig_registry_list_subkeys",
        "List subkey names under a Windows Registry key.",
        {"root": {"type": "string", "enum": _ROOT_ENUM}, "key_path": {"type": "string"}},
        ["root", "key_path"],
    ),
    _tool(
        "sysconfig_registry_search",
        "Recursively search a Windows Registry subtree for value names/data or subkey names "
        "containing a query string. Bounded by max_depth/max_results.",
        {
            "root": {"type": "string", "enum": _ROOT_ENUM},
            "key_path": {"type": "string"},
            "query": {"type": "string"},
            "search_values": {"type": "boolean"},
            "search_names": {"type": "boolean"},
            "max_depth": {"type": "integer"},
            "max_results": {"type": "integer"},
        },
        ["root", "key_path", "query"],
    ),
    _tool(
        "sysconfig_registry_snapshot_key",
        "Recursively dump a Windows Registry key's values and subkeys as a nested snapshot.",
        {
            "root": {"type": "string", "enum": _ROOT_ENUM},
            "key_path": {"type": "string"},
            "max_depth": {"type": "integer"},
        },
        ["root", "key_path"],
    ),
    _tool(
        "sysconfig_registry_set_value",
        "Create/overwrite a Windows Registry value (HKCU only). First call previews the change; "
        "call again with confirm=true to apply it.",
        {
            "root": {"type": "string", "enum": _ROOT_ENUM},
            "key_path": {"type": "string"},
            "value_name": {"type": "string"},
            "value": {"type": "string"},
            "value_type": {"type": "string", "enum": _REG_TYPE_ENUM},
            "confirm": {"type": "boolean"},
        },
        ["root", "key_path", "value_name", "value"],
    ),
    _tool(
        "sysconfig_registry_create_key",
        "Create a Windows Registry key (HKCU only). Confirm-gated.",
        {
            "root": {"type": "string", "enum": _ROOT_ENUM},
            "key_path": {"type": "string"},
            "confirm": {"type": "boolean"},
        },
        ["root", "key_path"],
    ),
    _tool(
        "sysconfig_registry_delete_value",
        "Delete a single Windows Registry value (HKCU only). Confirm-gated.",
        {
            "root": {"type": "string", "enum": _ROOT_ENUM},
            "key_path": {"type": "string"},
            "value_name": {"type": "string"},
            "confirm": {"type": "boolean"},
        },
        ["root", "key_path", "value_name"],
    ),
    _tool(
        "sysconfig_registry_delete_key",
        "Delete a Windows Registry key and its values (HKCU only, key must have no subkeys). " "Confirm-gated.",
        {
            "root": {"type": "string", "enum": _ROOT_ENUM},
            "key_path": {"type": "string"},
            "confirm": {"type": "boolean"},
        },
        ["root", "key_path"],
    ),
    # -- RegistryBackup --
    _tool(
        "sysconfig_registry_backup_json",
        "Snapshot a Windows Registry key (and everything under it) to a timestamped JSON backup file.",
        {"root": {"type": "string", "enum": _ROOT_ENUM}, "key_path": {"type": "string"}},
        ["root", "key_path"],
    ),
    _tool(
        "sysconfig_registry_list_backups",
        "List previously created registry backup files (JSON and .reg).",
    ),
    _tool(
        "sysconfig_registry_restore_json",
        "Restore a JSON registry backup by replaying its values (HKCU only). Confirm-gated.",
        {"backup_path": {"type": "string"}, "confirm": {"type": "boolean"}},
        ["backup_path"],
    ),
    _tool(
        "sysconfig_registry_export_reg_file",
        "Export a Windows Registry key to a native .reg file via reg.exe.",
        {
            "root": {"type": "string", "enum": _ROOT_ENUM},
            "key_path": {"type": "string"},
            "out_path": {"type": "string"},
        },
        ["root", "key_path"],
    ),
    _tool(
        "sysconfig_registry_import_reg_file",
        "Import a .reg file via reg.exe. Applies whatever roots/keys the file itself specifies. " "Confirm-gated.",
        {"reg_file_path": {"type": "string"}, "confirm": {"type": "boolean"}},
        ["reg_file_path"],
    ),
    # -- EnvironmentVariables --
    _tool(
        "sysconfig_env_get",
        "Read an environment variable from the current process's environment.",
        {"name": {"type": "string"}},
        ["name"],
    ),
    _tool(
        "sysconfig_env_list",
        "List environment variables in the current process's environment, optionally filtered " "by name prefix.",
        {"filter_prefix": {"type": "string"}},
    ),
    _tool(
        "sysconfig_env_set",
        "Persist an environment variable via setx (user or system scope). Only affects new "
        "processes. Confirm-gated.",
        {
            "name": {"type": "string"},
            "value": {"type": "string"},
            "scope": {"type": "string", "enum": ["user", "system"]},
            "confirm": {"type": "boolean"},
        },
        ["name", "value"],
    ),
    _tool(
        "sysconfig_env_delete",
        "Delete a persisted environment variable (user or system scope). Confirm-gated.",
        {
            "name": {"type": "string"},
            "scope": {"type": "string", "enum": ["user", "system"]},
            "confirm": {"type": "boolean"},
        },
        ["name"],
    ),
    # -- SystemProperties --
    _tool(
        "sysconfig_get_computer_info",
        "Get computer name, domain/workgroup, OS version/build, manufacturer/model, and RAM.",
    ),
    _tool(
        "sysconfig_get_performance_options",
        "Get the current visual-effects performance setting (best appearance/performance/custom).",
    ),
    _tool(
        "sysconfig_get_virtual_memory_info",
        "Get current page file(s): location, allocated/current size.",
    ),
    _tool(
        "sysconfig_get_system_protection_status",
        "Get recent System Restore points.",
    ),
    _tool(
        "sysconfig_set_computer_description",
        "Set the cosmetic computer-description field (not the computer name). Confirm-gated, needs admin.",
        {"description": {"type": "string"}, "confirm": {"type": "boolean"}},
        ["description"],
    ),
    _tool(
        "sysconfig_open_system_properties_dialog",
        "Open the classic System Properties dialog (sysdm.cpl), optionally on a specific tab.",
        {
            "tab": {
                "type": "string",
                "enum": ["general", "computer_name", "hardware", "advanced", "system_protection", "remote"],
            }
        },
    ),
    # -- DeviceManagerControl --
    _tool(
        "sysconfig_device_list",
        "List devices, optionally filtered to only problem devices and/or by device class.",
        {"only_problems": {"type": "boolean"}, "device_class": {"type": "string"}},
    ),
    _tool(
        "sysconfig_device_get_details",
        "Get the full property set for one device by its InstanceId.",
        {"instance_id": {"type": "string"}},
        ["instance_id"],
    ),
    _tool(
        "sysconfig_device_get_driver_info",
        "Get driver version/provider/date for one device by its InstanceId.",
        {"instance_id": {"type": "string"}},
        ["instance_id"],
    ),
    _tool(
        "sysconfig_device_rescan_hardware",
        "Trigger a 'scan for hardware changes' equivalent (pnputil /scan-devices).",
    ),
    _tool(
        "sysconfig_device_enable",
        "Enable a disabled device by its InstanceId. Needs admin. Confirm-gated.",
        {"instance_id": {"type": "string"}, "confirm": {"type": "boolean"}},
        ["instance_id"],
    ),
    _tool(
        "sysconfig_device_disable",
        "Disable a device by its InstanceId. Needs admin. Confirm-gated - be careful not to "
        "disable a device the system needs (keyboard/network adapter).",
        {"instance_id": {"type": "string"}, "confirm": {"type": "boolean"}},
        ["instance_id"],
    ),
    # -- WindowsUpdate --
    _tool(
        "sysconfig_update_check",
        "Search for available (not yet installed) Windows software updates.",
    ),
    _tool(
        "sysconfig_update_list_history",
        "List recently installed Windows updates.",
        {"count": {"type": "integer"}},
    ),
    _tool(
        "sysconfig_update_is_restart_required",
        "Check whether a pending Windows Update needs a restart to finish applying.",
    ),
    _tool(
        "sysconfig_update_install",
        "Download and install all available Windows software updates. Needs admin, does not "
        "auto-restart. Confirm-gated.",
        {"confirm": {"type": "boolean"}},
    ),
    _tool(
        "sysconfig_update_pause",
        "Pause Windows Update for up to 35 days. Confirm-gated.",
        {"days": {"type": "integer"}, "confirm": {"type": "boolean"}},
    ),
    # -- SystemRestore --
    _tool(
        "sysconfig_restore_list_points",
        "List available System Restore points (sequence number, description, creation time, type).",
    ),
    _tool(
        "sysconfig_restore_create_point",
        "Create a new System Restore point. Needs admin. Confirm-gated.",
        {"description": {"type": "string"}, "confirm": {"type": "boolean"}},
    ),
    _tool(
        "sysconfig_restore_to_point",
        "Restore the system to a prior restore point by sequence number (from "
        "sysconfig_restore_list_points). DESTRUCTIVE - reboots the machine immediately and "
        "reverts system files/registry/installed programs. Needs admin. Confirm-gated.",
        {"sequence_number": {"type": "integer"}, "confirm": {"type": "boolean"}},
        ["sequence_number"],
    ),
    _tool(
        "sysconfig_restore_get_protection_status",
        "Check whether System Restore protection is currently on for a drive.",
        {"drive": {"type": "string"}},
    ),
    _tool(
        "sysconfig_restore_enable_protection",
        "Turn System Restore protection ON for a drive. Needs admin. Confirm-gated.",
        {"drive": {"type": "string"}, "confirm": {"type": "boolean"}},
    ),
    _tool(
        "sysconfig_restore_disable_protection",
        "Turn System Restore protection OFF for a drive. Needs admin. Confirm-gated.",
        {"drive": {"type": "string"}, "confirm": {"type": "boolean"}},
    ),
    # -- BiosUefi --
    _tool(
        "sysconfig_bios_get_info",
        "Get BIOS manufacturer, version, serial number, and release date.",
    ),
    _tool(
        "sysconfig_bios_get_firmware_type",
        "Check whether the machine boots via legacy BIOS or UEFI firmware.",
    ),
    _tool(
        "sysconfig_bios_get_secure_boot_status",
        "Check Secure Boot on/off status (UEFI only).",
    ),
    _tool(
        "sysconfig_bios_get_tpm_status",
        "Check TPM presence/version/enabled state.",
    ),
    _tool(
        "sysconfig_bios_get_firmware_summary",
        "Get BIOS info, firmware type, Secure Boot, and TPM status in one call.",
    ),
    _tool(
        "sysconfig_bios_restart_to_firmware_settings",
        "Reboot the machine immediately into UEFI firmware setup. Confirm-gated.",
        {"confirm": {"type": "boolean"}},
    ),
]

# ---------------------------------------------------------------------------
# Direct handlers - flat name -> lambda(args_dict) -> result dict
# ---------------------------------------------------------------------------
SYSTEM_CONFIG_DIRECT_HANDLERS = {
    # -- RegistryManager --
    "sysconfig_registry_get_value": lambda d, _k="registry_manager", _m="get_value", _p=[
        "root",
        "key_path",
        "value_name",
    ]: getattr(_get(_k), _m)(**_pick(d, _p)),
    "sysconfig_registry_list_values": lambda d, _k="registry_manager", _m="list_values", _p=[
        "root",
        "key_path",
    ]: getattr(_get(_k), _m)(**_pick(d, _p)),
    "sysconfig_registry_list_subkeys": lambda d, _k="registry_manager", _m="list_subkeys", _p=[
        "root",
        "key_path",
    ]: getattr(_get(_k), _m)(**_pick(d, _p)),
    "sysconfig_registry_search": lambda d, _k="registry_manager", _m="search_key", _p=[
        "root",
        "key_path",
        "query",
        "search_values",
        "search_names",
        "max_depth",
        "max_results",
    ]: getattr(_get(_k), _m)(**_pick(d, _p)),
    "sysconfig_registry_snapshot_key": lambda d, _k="registry_manager", _m="snapshot_key", _p=[
        "root",
        "key_path",
        "max_depth",
    ]: getattr(_get(_k), _m)(**_pick(d, _p)),
    "sysconfig_registry_set_value": lambda d, _k="registry_manager", _m="set_value", _p=[
        "root",
        "key_path",
        "value_name",
        "value",
        "value_type",
        "confirm",
    ]: getattr(_get(_k), _m)(**_pick(d, _p)),
    "sysconfig_registry_create_key": lambda d, _k="registry_manager", _m="create_key", _p=[
        "root",
        "key_path",
        "confirm",
    ]: getattr(_get(_k), _m)(**_pick(d, _p)),
    "sysconfig_registry_delete_value": lambda d, _k="registry_manager", _m="delete_value", _p=[
        "root",
        "key_path",
        "value_name",
        "confirm",
    ]: getattr(_get(_k), _m)(**_pick(d, _p)),
    "sysconfig_registry_delete_key": lambda d, _k="registry_manager", _m="delete_key", _p=[
        "root",
        "key_path",
        "confirm",
    ]: getattr(_get(_k), _m)(**_pick(d, _p)),
    # -- RegistryBackup --
    "sysconfig_registry_backup_json": lambda d, _k="registry_backup", _m="backup_key_json", _p=[
        "root",
        "key_path",
    ]: getattr(_get(_k), _m)(**_pick(d, _p)),
    "sysconfig_registry_list_backups": lambda d, _k="registry_backup", _m="list_backups", _p=[]: getattr(_get(_k), _m)(
        **_pick(d, _p)
    ),
    "sysconfig_registry_restore_json": lambda d, _k="registry_backup", _m="restore_key_json", _p=[
        "backup_path",
        "confirm",
    ]: getattr(_get(_k), _m)(**_pick(d, _p)),
    "sysconfig_registry_export_reg_file": lambda d, _k="registry_backup", _m="export_reg_file", _p=[
        "root",
        "key_path",
        "out_path",
    ]: getattr(_get(_k), _m)(**_pick(d, _p)),
    "sysconfig_registry_import_reg_file": lambda d, _k="registry_backup", _m="import_reg_file", _p=[
        "reg_file_path",
        "confirm",
    ]: getattr(_get(_k), _m)(**_pick(d, _p)),
    # -- EnvironmentVariables --
    "sysconfig_env_get": lambda d, _k="env_vars", _m="get_variable", _p=["name"]: getattr(_get(_k), _m)(**_pick(d, _p)),
    "sysconfig_env_list": lambda d, _k="env_vars", _m="list_variables", _p=["filter_prefix"]: getattr(_get(_k), _m)(
        **_pick(d, _p)
    ),
    "sysconfig_env_set": lambda d, _k="env_vars", _m="set_variable", _p=["name", "value", "scope", "confirm"]: getattr(
        _get(_k), _m
    )(**_pick(d, _p)),
    "sysconfig_env_delete": lambda d, _k="env_vars", _m="delete_variable", _p=["name", "scope", "confirm"]: getattr(
        _get(_k), _m
    )(**_pick(d, _p)),
    # -- SystemProperties --
    "sysconfig_get_computer_info": lambda d, _k="system_properties", _m="get_computer_info", _p=[]: getattr(
        _get(_k), _m
    )(**_pick(d, _p)),
    "sysconfig_get_performance_options": lambda d, _k="system_properties", _m="get_performance_options", _p=[]: getattr(
        _get(_k), _m
    )(**_pick(d, _p)),
    "sysconfig_get_virtual_memory_info": lambda d, _k="system_properties", _m="get_virtual_memory_info", _p=[]: getattr(
        _get(_k), _m
    )(**_pick(d, _p)),
    "sysconfig_get_system_protection_status": lambda d, _k="system_properties", _m="get_system_protection_status", _p=[]: getattr(
        _get(_k), _m
    )(
        **_pick(d, _p)
    ),
    "sysconfig_set_computer_description": lambda d, _k="system_properties", _m="set_computer_description", _p=[
        "description",
        "confirm",
    ]: getattr(_get(_k), _m)(**_pick(d, _p)),
    "sysconfig_open_system_properties_dialog": lambda d, _k="system_properties", _m="open_system_properties_dialog", _p=[
        "tab"
    ]: getattr(
        _get(_k), _m
    )(
        **_pick(d, _p)
    ),
    # -- DeviceManagerControl --
    "sysconfig_device_list": lambda d, _k="device_manager", _m="list_devices", _p=[
        "only_problems",
        "device_class",
    ]: getattr(_get(_k), _m)(**_pick(d, _p)),
    "sysconfig_device_get_details": lambda d, _k="device_manager", _m="get_device_details", _p=["instance_id"]: getattr(
        _get(_k), _m
    )(**_pick(d, _p)),
    "sysconfig_device_get_driver_info": lambda d, _k="device_manager", _m="get_driver_info", _p=[
        "instance_id"
    ]: getattr(_get(_k), _m)(**_pick(d, _p)),
    "sysconfig_device_rescan_hardware": lambda d, _k="device_manager", _m="rescan_hardware", _p=[]: getattr(
        _get(_k), _m
    )(**_pick(d, _p)),
    "sysconfig_device_enable": lambda d, _k="device_manager", _m="enable_device", _p=[
        "instance_id",
        "confirm",
    ]: getattr(_get(_k), _m)(**_pick(d, _p)),
    "sysconfig_device_disable": lambda d, _k="device_manager", _m="disable_device", _p=[
        "instance_id",
        "confirm",
    ]: getattr(_get(_k), _m)(**_pick(d, _p)),
    # -- WindowsUpdate --
    "sysconfig_update_check": lambda d, _k="windows_update", _m="check_for_updates", _p=[]: getattr(_get(_k), _m)(
        **_pick(d, _p)
    ),
    "sysconfig_update_list_history": lambda d, _k="windows_update", _m="list_update_history", _p=["count"]: getattr(
        _get(_k), _m
    )(**_pick(d, _p)),
    "sysconfig_update_is_restart_required": lambda d, _k="windows_update", _m="is_restart_required", _p=[]: getattr(
        _get(_k), _m
    )(**_pick(d, _p)),
    "sysconfig_update_install": lambda d, _k="windows_update", _m="install_updates", _p=["confirm"]: getattr(
        _get(_k), _m
    )(**_pick(d, _p)),
    "sysconfig_update_pause": lambda d, _k="windows_update", _m="pause_updates", _p=["days", "confirm"]: getattr(
        _get(_k), _m
    )(**_pick(d, _p)),
    # -- SystemRestore --
    "sysconfig_restore_list_points": lambda d, _k="system_restore", _m="list_restore_points", _p=[]: getattr(
        _get(_k), _m
    )(**_pick(d, _p)),
    "sysconfig_restore_create_point": lambda d, _k="system_restore", _m="create_restore_point", _p=[
        "description",
        "confirm",
    ]: getattr(_get(_k), _m)(**_pick(d, _p)),
    "sysconfig_restore_to_point": lambda d, _k="system_restore", _m="restore_to_point", _p=[
        "sequence_number",
        "confirm",
    ]: getattr(_get(_k), _m)(**_pick(d, _p)),
    "sysconfig_restore_get_protection_status": lambda d, _k="system_restore", _m="get_protection_status", _p=[
        "drive"
    ]: getattr(_get(_k), _m)(**_pick(d, _p)),
    "sysconfig_restore_enable_protection": lambda d, _k="system_restore", _m="enable_protection", _p=[
        "drive",
        "confirm",
    ]: getattr(_get(_k), _m)(**_pick(d, _p)),
    "sysconfig_restore_disable_protection": lambda d, _k="system_restore", _m="disable_protection", _p=[
        "drive",
        "confirm",
    ]: getattr(_get(_k), _m)(**_pick(d, _p)),
    # -- BiosUefi --
    "sysconfig_bios_get_info": lambda d, _k="bios_uefi", _m="get_bios_info", _p=[]: getattr(_get(_k), _m)(
        **_pick(d, _p)
    ),
    "sysconfig_bios_get_firmware_type": lambda d, _k="bios_uefi", _m="get_firmware_type", _p=[]: getattr(_get(_k), _m)(
        **_pick(d, _p)
    ),
    "sysconfig_bios_get_secure_boot_status": lambda d, _k="bios_uefi", _m="get_secure_boot_status", _p=[]: getattr(
        _get(_k), _m
    )(**_pick(d, _p)),
    "sysconfig_bios_get_tpm_status": lambda d, _k="bios_uefi", _m="get_tpm_status", _p=[]: getattr(_get(_k), _m)(
        **_pick(d, _p)
    ),
    "sysconfig_bios_get_firmware_summary": lambda d, _k="bios_uefi", _m="get_firmware_summary", _p=[]: getattr(
        _get(_k), _m
    )(**_pick(d, _p)),
    "sysconfig_bios_restart_to_firmware_settings": lambda d, _k="bios_uefi", _m="restart_to_firmware_settings", _p=[
        "confirm"
    ]: getattr(_get(_k), _m)(**_pick(d, _p)),
}
