"""Storage Control tool registry
=================================
Wires system_control/storage/* (disk/partition management, volume
formatting and filesystem control) into the AI tool-calling loop. Same
pattern as ai/security_control_tools.py and ai/network_control_tools.py:
lazy singletons + a flat STORAGE_CONTROL_TOOLS / STORAGE_CONTROL_
DIRECT_HANDLERS pair, merged at the bottom of ai/tools_schema.py and
ai/tool_runtime.py respectively.

Naming: every tool is prefixed `storagectl_`, one segment per
underlying module - `storagectl_partition_*`, `storagectl_format_*`,
`storagectl_sense_*` (storage_sense.py), `storagectl_cloud_*`
(cloud_sync.py), `storagectl_quota_*` (disk_quota.py),
`storagectl_raid_*` (raid_manager.py), `storagectl_image_*`
(iso_vhd_mount.py), `storagectl_usb_*` (usb_eject.py).

Most state-changing methods here are confirm-gated because they touch
the partition table, erase data outright, claim disks into a pool, or
interrupt a running sync (see the docstrings in each system_control/
storage/*.py module for exactly which and why) - this mirrors the
underlying classes' own confirm-gating choices rather than gating
everything uniformly.
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

    if key == "partition":
        from system_control.storage.partition_manager import PartitionManager

        obj = PartitionManager()
    elif key == "format":
        from system_control.storage.format_manager import FormatManager

        obj = FormatManager()
    elif key == "sense":
        from system_control.storage.storage_sense import StorageSense

        obj = StorageSense()
    elif key == "cloud":
        from system_control.storage.cloud_sync import CloudSyncManager

        obj = CloudSyncManager()
    elif key == "quota":
        from system_control.storage.disk_quota import DiskQuotaManager

        obj = DiskQuotaManager()
    elif key == "raid":
        from system_control.storage.raid_manager import RaidManager

        obj = RaidManager()
    elif key == "image":
        from system_control.storage.iso_vhd_mount import IsoVhdMount

        obj = IsoVhdMount()
    elif key == "usb":
        from system_control.storage.usb_eject import UsbEjectManager

        obj = UsbEjectManager()
    else:
        raise KeyError(f"Unknown storage_control tool key: {key}")

    _instances[key] = obj
    return obj


# ---------------------------------------------------------------------------
# Tool schemas
# ---------------------------------------------------------------------------
STORAGE_CONTROL_TOOLS = [
    # -- PartitionManager --
    _tool(
        "storagectl_partition_list_disks",
        "List every physical disk: number, friendly name, size, partition style, and health status.",
    ),
    _tool(
        "storagectl_partition_get_disk_info",
        "Get details for one disk by its Get-Disk number.",
        {"disk_number": {"type": "integer"}},
        ["disk_number"],
    ),
    _tool(
        "storagectl_partition_list_partitions",
        "List partitions, optionally filtered to one disk number.",
        {"disk_number": {"type": "integer"}},
    ),
    _tool(
        "storagectl_partition_get_partition_info",
        "Get details for one partition (drive letter, size, type, boot/system/active flags).",
        {"disk_number": {"type": "integer"}, "partition_number": {"type": "integer"}},
        ["disk_number", "partition_number"],
    ),
    _tool(
        "storagectl_partition_list_volumes",
        "List volumes: drive letter, label, filesystem, size, and free space.",
    ),
    _tool(
        "storagectl_partition_get_free_space",
        "Read total size and remaining free space for a drive letter.",
        {"drive_letter": {"type": "string"}},
        ["drive_letter"],
    ),
    _tool(
        "storagectl_partition_get_resize_limits",
        "Read the min/max size a partition can be resized to right now.",
        {"disk_number": {"type": "integer"}, "partition_number": {"type": "integer"}},
        ["disk_number", "partition_number"],
    ),
    _tool(
        "storagectl_partition_resize",
        "Resize (shrink/extend) a partition to an exact byte size. Confirm-gated, needs admin.",
        {
            "disk_number": {"type": "integer"},
            "partition_number": {"type": "integer"},
            "new_size_bytes": {"type": "integer"},
            "confirm": {"type": "boolean"},
        },
        ["disk_number", "partition_number", "new_size_bytes"],
    ),
    _tool(
        "storagectl_partition_assign_drive_letter",
        "Assign a drive letter to a partition. Confirm-gated, needs admin.",
        {
            "disk_number": {"type": "integer"},
            "partition_number": {"type": "integer"},
            "letter": {"type": "string"},
            "confirm": {"type": "boolean"},
        },
        ["disk_number", "partition_number", "letter"],
    ),
    _tool(
        "storagectl_partition_remove_drive_letter",
        "Remove a partition's drive letter. Confirm-gated, needs admin.",
        {"disk_number": {"type": "integer"}, "partition_number": {"type": "integer"}, "confirm": {"type": "boolean"}},
        ["disk_number", "partition_number"],
    ),
    _tool(
        "storagectl_partition_create",
        "Create a new partition in a disk's unallocated space. Confirm-gated, needs admin.",
        {
            "disk_number": {"type": "integer"},
            "size_bytes": {"type": "integer"},
            "use_max_size": {"type": "boolean"},
            "drive_letter": {"type": "string"},
            "confirm": {"type": "boolean"},
        },
        ["disk_number"],
    ),
    _tool(
        "storagectl_partition_delete",
        "Permanently delete a partition and ALL its data. Confirm-gated, destructive, needs admin.",
        {"disk_number": {"type": "integer"}, "partition_number": {"type": "integer"}, "confirm": {"type": "boolean"}},
        ["disk_number", "partition_number"],
    ),
    _tool(
        "storagectl_partition_initialize_disk",
        "Initialize a raw disk with a new partition table (GPT/MBR), WIPING any existing one. Confirm-gated, destructive, needs admin.",
        {"disk_number": {"type": "integer"}, "style": {"type": "string"}, "confirm": {"type": "boolean"}},
        ["disk_number"],
    ),
    _tool(
        "storagectl_partition_set_active",
        "Mark an MBR partition active/inactive (BIOS-boot flag). Confirm-gated - can affect bootability.",
        {
            "disk_number": {"type": "integer"},
            "partition_number": {"type": "integer"},
            "active": {"type": "boolean"},
            "confirm": {"type": "boolean"},
        },
        ["disk_number", "partition_number"],
    ),
    # -- FormatManager --
    _tool(
        "storagectl_format_get_volume_info",
        "Read a volume's filesystem, label, size, free space, and health status.",
        {"drive_letter": {"type": "string"}},
        ["drive_letter"],
    ),
    _tool(
        "storagectl_format_get_filesystem_type",
        "Read just a volume's filesystem type (NTFS/FAT32/exFAT/ReFS).",
        {"drive_letter": {"type": "string"}},
        ["drive_letter"],
    ),
    _tool(
        "storagectl_format_get_allocation_unit_size",
        "Read a volume's allocation unit (cluster) size in bytes.",
        {"drive_letter": {"type": "string"}},
        ["drive_letter"],
    ),
    _tool(
        "storagectl_format_set_volume_label",
        "Rename a volume's label. Not confirm-gated - cosmetic and reversible.",
        {"drive_letter": {"type": "string"}, "label": {"type": "string"}},
        ["drive_letter", "label"],
    ),
    _tool(
        "storagectl_format_volume",
        "Format a volume, ERASING ALL ITS DATA, with a new filesystem/label. Confirm-gated, needs admin.",
        {
            "drive_letter": {"type": "string"},
            "file_system": {"type": "string"},
            "label": {"type": "string"},
            "quick": {"type": "boolean"},
            "allocation_unit_size_bytes": {"type": "integer"},
            "confirm": {"type": "boolean"},
        },
        ["drive_letter"],
    ),
    _tool(
        "storagectl_format_convert_filesystem",
        "Convert a FAT32/exFAT volume to NTFS in place, preserving files. One-way. Confirm-gated, needs admin.",
        {"drive_letter": {"type": "string"}, "target_file_system": {"type": "string"}, "confirm": {"type": "boolean"}},
        ["drive_letter"],
    ),
    _tool(
        "storagectl_format_check_disk",
        "Run chkdsk on a volume. Read-only scan by default; fix_errors=True is confirm-gated and needs admin.",
        {"drive_letter": {"type": "string"}, "fix_errors": {"type": "boolean"}, "confirm": {"type": "boolean"}},
        ["drive_letter"],
    ),
    # -- StorageSense --
    _tool(
        "storagectl_sense_get_status",
        "Read every Storage Sense automatic-cleanup policy value (enabled, run frequency, temp files, recycle bin, downloads, cloud content).",
    ),
    _tool(
        "storagectl_sense_set_enabled",
        "Turn Windows Storage Sense on or off entirely.",
        {"enabled": {"type": "boolean"}},
        ["enabled"],
    ),
    _tool(
        "storagectl_sense_set_run_frequency",
        "Set how often Storage Sense runs automatically: 0=low disk space, 1=daily, 7=weekly, 30=monthly.",
        {"days": {"type": "integer"}},
        ["days"],
    ),
    _tool(
        "storagectl_sense_configure_temp_files",
        "Toggle cleanup of Storage Sense's own temporary files.",
        {"enabled": {"type": "boolean"}},
        ["enabled"],
    ),
    _tool(
        "storagectl_sense_configure_recycle_bin",
        "Set days before old Recycle Bin items are auto-deleted (0=never, or 1/14/30/60).",
        {"days": {"type": "integer"}},
        ["days"],
    ),
    _tool(
        "storagectl_sense_configure_downloads_cleanup",
        "Set days before untouched Downloads files are auto-deleted (0=never, or 1/14/30/60).",
        {"days": {"type": "integer"}},
        ["days"],
    ),
    _tool(
        "storagectl_sense_configure_cloud_content",
        "Set days of inactivity before local cloud files (e.g. OneDrive) become online-only (0=never, or 1/14/30/60).",
        {"days": {"type": "integer"}},
        ["days"],
    ),
    _tool(
        "storagectl_sense_run_now",
        "Trigger the Storage Sense scheduled task to run cleanup immediately.",
    ),
    # -- CloudSyncManager --
    _tool(
        "storagectl_cloud_list_providers",
        "List supported cloud-sync providers (onedrive, googledrive, dropbox) and whether each is running.",
    ),
    _tool(
        "storagectl_cloud_get_status",
        "Check whether a specific cloud-sync provider's client process is running.",
        {"provider": {"type": "string", "enum": ["onedrive", "googledrive", "dropbox"]}},
        ["provider"],
    ),
    _tool(
        "storagectl_cloud_get_onedrive_folder",
        "Read OneDrive's synced root folder path from the registry (personal account).",
    ),
    _tool(
        "storagectl_cloud_pause_sync",
        "Stop syncing by ending a cloud provider's client process. Confirm-gated.",
        {
            "provider": {"type": "string", "enum": ["onedrive", "googledrive", "dropbox"]},
            "confirm": {"type": "boolean"},
        },
        ["provider"],
    ),
    _tool(
        "storagectl_cloud_resume_sync",
        "Relaunch a cloud provider's client process to resume syncing. Confirm-gated.",
        {
            "provider": {"type": "string", "enum": ["onedrive", "googledrive", "dropbox"]},
            "confirm": {"type": "boolean"},
        },
        ["provider"],
    ),
    # -- DiskQuotaManager --
    _tool(
        "storagectl_quota_query",
        "Read quota tracking/enforcement state and every user's usage/limits on a volume. Needs admin.",
        {"volume": {"type": "string"}},
        ["volume"],
    ),
    _tool(
        "storagectl_quota_enable_tracking",
        "Enable quota tracking (measurement only, no enforcement) on a volume. Confirm-gated, needs admin.",
        {"volume": {"type": "string"}, "confirm": {"type": "boolean"}},
        ["volume"],
    ),
    _tool(
        "storagectl_quota_enable_enforcement",
        "Enable quota enforcement on a volume - users over their limit are blocked from writing. Confirm-gated, needs admin.",
        {"volume": {"type": "string"}, "confirm": {"type": "boolean"}},
        ["volume"],
    ),
    _tool(
        "storagectl_quota_disable",
        "Disable disk quotas entirely on a volume. Confirm-gated, needs admin.",
        {"volume": {"type": "string"}, "confirm": {"type": "boolean"}},
        ["volume"],
    ),
    _tool(
        "storagectl_quota_set_user_quota",
        "Set one user's warning threshold and hard limit (in bytes) on a volume. Confirm-gated, needs admin.",
        {
            "volume": {"type": "string"},
            "username": {"type": "string"},
            "warning_bytes": {"type": "integer"},
            "limit_bytes": {"type": "integer"},
            "confirm": {"type": "boolean"},
        },
        ["volume", "username", "warning_bytes", "limit_bytes"],
    ),
    _tool(
        "storagectl_quota_list_violations",
        "List all users currently over their quota warning or limit threshold, across all volumes.",
    ),
    # -- RaidManager (Storage Spaces) --
    _tool(
        "storagectl_raid_list_physical_disks",
        "List physical disks visible to Storage Spaces, including which are available to be pooled.",
    ),
    _tool(
        "storagectl_raid_list_storage_pools",
        "List storage pools: name, size, allocated size, and health.",
    ),
    _tool(
        "storagectl_raid_get_storage_pool_info",
        "Get details for one storage pool by friendly name.",
        {"name": {"type": "string"}},
        ["name"],
    ),
    _tool(
        "storagectl_raid_create_storage_pool",
        "Create a new storage pool from one or more unpooled physical disks. Confirm-gated, destructive, needs admin.",
        {
            "name": {"type": "string"},
            "physical_disk_friendly_names": {"type": "array", "items": {"type": "string"}},
            "confirm": {"type": "boolean"},
        },
        ["name", "physical_disk_friendly_names"],
    ),
    _tool(
        "storagectl_raid_remove_storage_pool",
        "Permanently delete a storage pool and every virtual disk/data on it. Confirm-gated, destructive, needs admin.",
        {"name": {"type": "string"}, "confirm": {"type": "boolean"}},
        ["name"],
    ),
    _tool(
        "storagectl_raid_list_virtual_disks",
        "List virtual disks: name, size, resiliency type (Simple/Mirror/Parity), and health.",
    ),
    _tool(
        "storagectl_raid_create_virtual_disk",
        "Create a new virtual disk on a storage pool with a given resiliency (Simple/Mirror/Parity). Confirm-gated, needs admin.",
        {
            "pool_name": {"type": "string"},
            "name": {"type": "string"},
            "resiliency": {"type": "string", "enum": ["Simple", "Mirror", "Parity"]},
            "size_bytes": {"type": "integer"},
            "use_max_size": {"type": "boolean"},
            "confirm": {"type": "boolean"},
        },
        ["pool_name", "name"],
    ),
    _tool(
        "storagectl_raid_get_virtual_disk_health",
        "Read a virtual disk's health and operational status.",
        {"name": {"type": "string"}},
        ["name"],
    ),
    _tool(
        "storagectl_raid_repair_virtual_disk",
        "Trigger a repair of a degraded virtual disk. Confirm-gated, needs admin.",
        {"name": {"type": "string"}, "confirm": {"type": "boolean"}},
        ["name"],
    ),
    _tool(
        "storagectl_raid_remove_virtual_disk",
        "Permanently delete a virtual disk and all its data. Confirm-gated, destructive, needs admin.",
        {"name": {"type": "string"}, "confirm": {"type": "boolean"}},
        ["name"],
    ),
    # -- IsoVhdMount --
    _tool(
        "storagectl_image_mount",
        "Mount an ISO or VHD/VHDX, attaching it as a new disk with its own drive letter.",
        {"path": {"type": "string"}, "read_only": {"type": "boolean"}},
        ["path"],
    ),
    _tool(
        "storagectl_image_dismount",
        "Dismount a previously mounted ISO or VHD/VHDX by its file path.",
        {"path": {"type": "string"}},
        ["path"],
    ),
    _tool(
        "storagectl_image_get_info",
        "Read a disk image's attach state, type (ISO/VHD/VHDX), and size.",
        {"path": {"type": "string"}},
        ["path"],
    ),
    _tool(
        "storagectl_image_list_mounted",
        "List every currently mounted (attached) disk image.",
    ),
    _tool(
        "storagectl_image_create_vhd",
        "Create a new blank VHD or VHDX file. Requires the Hyper-V PowerShell module.",
        {"path": {"type": "string"}, "size_bytes": {"type": "integer"}, "dynamic": {"type": "boolean"}},
        ["path", "size_bytes"],
    ),
    _tool(
        "storagectl_image_get_vhd_info",
        "Read a VHD/VHDX's size, attach state, and parent disk. Requires the Hyper-V PowerShell module.",
        {"path": {"type": "string"}},
        ["path"],
    ),
    _tool(
        "storagectl_image_resize_vhd",
        "Resize an existing VHD/VHDX. Confirm-gated. Requires the Hyper-V PowerShell module.",
        {"path": {"type": "string"}, "new_size_bytes": {"type": "integer"}, "confirm": {"type": "boolean"}},
        ["path", "new_size_bytes"],
    ),
    # -- UsbEjectManager --
    _tool(
        "storagectl_usb_list_removable_drives",
        "List every USB-attached disk and its mounted drive letter(s).",
    ),
    _tool(
        "storagectl_usb_get_drive_info",
        "Get details for one removable drive by drive letter, including its physical disk.",
        {"drive_letter": {"type": "string"}},
        ["drive_letter"],
    ),
    _tool(
        "storagectl_usb_eject_drive",
        "Safely eject a removable drive by drive letter. Confirm-gated.",
        {"drive_letter": {"type": "string"}, "confirm": {"type": "boolean"}},
        ["drive_letter"],
    ),
]

# ---------------------------------------------------------------------------
# Direct handlers - flat name -> lambda(args_dict) -> result dict
# ---------------------------------------------------------------------------
STORAGE_CONTROL_DIRECT_HANDLERS = {
    # -- PartitionManager --
    "storagectl_partition_list_disks": lambda d, _k="partition", _m="list_disks", _p=[]: getattr(_get(_k), _m)(
        **_pick(d, _p)
    ),
    "storagectl_partition_get_disk_info": lambda d, _k="partition", _m="get_disk_info", _p=["disk_number"]: getattr(
        _get(_k), _m
    )(**_pick(d, _p)),
    "storagectl_partition_list_partitions": lambda d, _k="partition", _m="list_partitions", _p=["disk_number"]: getattr(
        _get(_k), _m
    )(**_pick(d, _p)),
    "storagectl_partition_get_partition_info": lambda d, _k="partition", _m="get_partition_info", _p=[
        "disk_number",
        "partition_number",
    ]: getattr(_get(_k), _m)(**_pick(d, _p)),
    "storagectl_partition_list_volumes": lambda d, _k="partition", _m="list_volumes", _p=[]: getattr(_get(_k), _m)(
        **_pick(d, _p)
    ),
    "storagectl_partition_get_free_space": lambda d, _k="partition", _m="get_free_space", _p=["drive_letter"]: getattr(
        _get(_k), _m
    )(**_pick(d, _p)),
    "storagectl_partition_get_resize_limits": lambda d, _k="partition", _m="get_resize_limits", _p=[
        "disk_number",
        "partition_number",
    ]: getattr(_get(_k), _m)(**_pick(d, _p)),
    "storagectl_partition_resize": lambda d, _k="partition", _m="resize_partition", _p=[
        "disk_number",
        "partition_number",
        "new_size_bytes",
        "confirm",
    ]: getattr(_get(_k), _m)(**_pick(d, _p)),
    "storagectl_partition_assign_drive_letter": lambda d, _k="partition", _m="assign_drive_letter", _p=[
        "disk_number",
        "partition_number",
        "letter",
        "confirm",
    ]: getattr(_get(_k), _m)(**_pick(d, _p)),
    "storagectl_partition_remove_drive_letter": lambda d, _k="partition", _m="remove_drive_letter", _p=[
        "disk_number",
        "partition_number",
        "confirm",
    ]: getattr(_get(_k), _m)(**_pick(d, _p)),
    "storagectl_partition_create": lambda d, _k="partition", _m="create_partition", _p=[
        "disk_number",
        "size_bytes",
        "use_max_size",
        "drive_letter",
        "confirm",
    ]: getattr(_get(_k), _m)(**_pick(d, _p)),
    "storagectl_partition_delete": lambda d, _k="partition", _m="delete_partition", _p=[
        "disk_number",
        "partition_number",
        "confirm",
    ]: getattr(_get(_k), _m)(**_pick(d, _p)),
    "storagectl_partition_initialize_disk": lambda d, _k="partition", _m="initialize_disk", _p=[
        "disk_number",
        "style",
        "confirm",
    ]: getattr(_get(_k), _m)(**_pick(d, _p)),
    "storagectl_partition_set_active": lambda d, _k="partition", _m="set_partition_active", _p=[
        "disk_number",
        "partition_number",
        "active",
        "confirm",
    ]: getattr(_get(_k), _m)(**_pick(d, _p)),
    # -- FormatManager --
    "storagectl_format_get_volume_info": lambda d, _k="format", _m="get_volume_info", _p=["drive_letter"]: getattr(
        _get(_k), _m
    )(**_pick(d, _p)),
    "storagectl_format_get_filesystem_type": lambda d, _k="format", _m="get_filesystem_type", _p=[
        "drive_letter"
    ]: getattr(_get(_k), _m)(**_pick(d, _p)),
    "storagectl_format_get_allocation_unit_size": lambda d, _k="format", _m="get_allocation_unit_size", _p=[
        "drive_letter"
    ]: getattr(_get(_k), _m)(**_pick(d, _p)),
    "storagectl_format_set_volume_label": lambda d, _k="format", _m="set_volume_label", _p=[
        "drive_letter",
        "label",
    ]: getattr(_get(_k), _m)(**_pick(d, _p)),
    "storagectl_format_volume": lambda d, _k="format", _m="format_volume", _p=[
        "drive_letter",
        "file_system",
        "label",
        "quick",
        "allocation_unit_size_bytes",
        "confirm",
    ]: getattr(_get(_k), _m)(**_pick(d, _p)),
    "storagectl_format_convert_filesystem": lambda d, _k="format", _m="convert_filesystem", _p=[
        "drive_letter",
        "target_file_system",
        "confirm",
    ]: getattr(_get(_k), _m)(**_pick(d, _p)),
    "storagectl_format_check_disk": lambda d, _k="format", _m="check_disk", _p=[
        "drive_letter",
        "fix_errors",
        "confirm",
    ]: getattr(_get(_k), _m)(**_pick(d, _p)),
    # -- StorageSense --
    "storagectl_sense_get_status": lambda d, _k="sense", _m="get_status", _p=[]: getattr(_get(_k), _m)(**_pick(d, _p)),
    "storagectl_sense_set_enabled": lambda d, _k="sense", _m="set_enabled", _p=["enabled"]: getattr(_get(_k), _m)(
        **_pick(d, _p)
    ),
    "storagectl_sense_set_run_frequency": lambda d, _k="sense", _m="set_run_frequency", _p=["days"]: getattr(
        _get(_k), _m
    )(**_pick(d, _p)),
    "storagectl_sense_configure_temp_files": lambda d, _k="sense", _m="configure_temp_files", _p=["enabled"]: getattr(
        _get(_k), _m
    )(**_pick(d, _p)),
    "storagectl_sense_configure_recycle_bin": lambda d, _k="sense", _m="configure_recycle_bin", _p=["days"]: getattr(
        _get(_k), _m
    )(**_pick(d, _p)),
    "storagectl_sense_configure_downloads_cleanup": lambda d, _k="sense", _m="configure_downloads_cleanup", _p=[
        "days"
    ]: getattr(_get(_k), _m)(**_pick(d, _p)),
    "storagectl_sense_configure_cloud_content": lambda d, _k="sense", _m="configure_cloud_content", _p=[
        "days"
    ]: getattr(_get(_k), _m)(**_pick(d, _p)),
    "storagectl_sense_run_now": lambda d, _k="sense", _m="run_now", _p=[]: getattr(_get(_k), _m)(**_pick(d, _p)),
    # -- CloudSyncManager --
    "storagectl_cloud_list_providers": lambda d, _k="cloud", _m="list_providers", _p=[]: getattr(_get(_k), _m)(
        **_pick(d, _p)
    ),
    "storagectl_cloud_get_status": lambda d, _k="cloud", _m="get_status", _p=["provider"]: getattr(_get(_k), _m)(
        **_pick(d, _p)
    ),
    "storagectl_cloud_get_onedrive_folder": lambda d, _k="cloud", _m="get_onedrive_folder", _p=[]: getattr(
        _get(_k), _m
    )(**_pick(d, _p)),
    "storagectl_cloud_pause_sync": lambda d, _k="cloud", _m="pause_sync", _p=["provider", "confirm"]: getattr(
        _get(_k), _m
    )(**_pick(d, _p)),
    "storagectl_cloud_resume_sync": lambda d, _k="cloud", _m="resume_sync", _p=["provider", "confirm"]: getattr(
        _get(_k), _m
    )(**_pick(d, _p)),
    # -- DiskQuotaManager --
    "storagectl_quota_query": lambda d, _k="quota", _m="query", _p=["volume"]: getattr(_get(_k), _m)(**_pick(d, _p)),
    "storagectl_quota_enable_tracking": lambda d, _k="quota", _m="enable_tracking", _p=["volume", "confirm"]: getattr(
        _get(_k), _m
    )(**_pick(d, _p)),
    "storagectl_quota_enable_enforcement": lambda d, _k="quota", _m="enable_enforcement", _p=[
        "volume",
        "confirm",
    ]: getattr(_get(_k), _m)(**_pick(d, _p)),
    "storagectl_quota_disable": lambda d, _k="quota", _m="disable", _p=["volume", "confirm"]: getattr(_get(_k), _m)(
        **_pick(d, _p)
    ),
    "storagectl_quota_set_user_quota": lambda d, _k="quota", _m="set_user_quota", _p=[
        "volume",
        "username",
        "warning_bytes",
        "limit_bytes",
        "confirm",
    ]: getattr(_get(_k), _m)(**_pick(d, _p)),
    "storagectl_quota_list_violations": lambda d, _k="quota", _m="list_violations", _p=[]: getattr(_get(_k), _m)(
        **_pick(d, _p)
    ),
    # -- RaidManager --
    "storagectl_raid_list_physical_disks": lambda d, _k="raid", _m="list_physical_disks", _p=[]: getattr(_get(_k), _m)(
        **_pick(d, _p)
    ),
    "storagectl_raid_list_storage_pools": lambda d, _k="raid", _m="list_storage_pools", _p=[]: getattr(_get(_k), _m)(
        **_pick(d, _p)
    ),
    "storagectl_raid_get_storage_pool_info": lambda d, _k="raid", _m="get_storage_pool_info", _p=["name"]: getattr(
        _get(_k), _m
    )(**_pick(d, _p)),
    "storagectl_raid_create_storage_pool": lambda d, _k="raid", _m="create_storage_pool", _p=[
        "name",
        "physical_disk_friendly_names",
        "confirm",
    ]: getattr(_get(_k), _m)(**_pick(d, _p)),
    "storagectl_raid_remove_storage_pool": lambda d, _k="raid", _m="remove_storage_pool", _p=[
        "name",
        "confirm",
    ]: getattr(_get(_k), _m)(**_pick(d, _p)),
    "storagectl_raid_list_virtual_disks": lambda d, _k="raid", _m="list_virtual_disks", _p=[]: getattr(_get(_k), _m)(
        **_pick(d, _p)
    ),
    "storagectl_raid_create_virtual_disk": lambda d, _k="raid", _m="create_virtual_disk", _p=[
        "pool_name",
        "name",
        "resiliency",
        "size_bytes",
        "use_max_size",
        "confirm",
    ]: getattr(_get(_k), _m)(**_pick(d, _p)),
    "storagectl_raid_get_virtual_disk_health": lambda d, _k="raid", _m="get_virtual_disk_health", _p=["name"]: getattr(
        _get(_k), _m
    )(**_pick(d, _p)),
    "storagectl_raid_repair_virtual_disk": lambda d, _k="raid", _m="repair_virtual_disk", _p=[
        "name",
        "confirm",
    ]: getattr(_get(_k), _m)(**_pick(d, _p)),
    "storagectl_raid_remove_virtual_disk": lambda d, _k="raid", _m="remove_virtual_disk", _p=[
        "name",
        "confirm",
    ]: getattr(_get(_k), _m)(**_pick(d, _p)),
    # -- IsoVhdMount --
    "storagectl_image_mount": lambda d, _k="image", _m="mount_image", _p=["path", "read_only"]: getattr(_get(_k), _m)(
        **_pick(d, _p)
    ),
    "storagectl_image_dismount": lambda d, _k="image", _m="dismount_image", _p=["path"]: getattr(_get(_k), _m)(
        **_pick(d, _p)
    ),
    "storagectl_image_get_info": lambda d, _k="image", _m="get_image_info", _p=["path"]: getattr(_get(_k), _m)(
        **_pick(d, _p)
    ),
    "storagectl_image_list_mounted": lambda d, _k="image", _m="list_mounted_images", _p=[]: getattr(_get(_k), _m)(
        **_pick(d, _p)
    ),
    "storagectl_image_create_vhd": lambda d, _k="image", _m="create_vhd", _p=["path", "size_bytes", "dynamic"]: getattr(
        _get(_k), _m
    )(**_pick(d, _p)),
    "storagectl_image_get_vhd_info": lambda d, _k="image", _m="get_vhd_info", _p=["path"]: getattr(_get(_k), _m)(
        **_pick(d, _p)
    ),
    "storagectl_image_resize_vhd": lambda d, _k="image", _m="resize_vhd", _p=[
        "path",
        "new_size_bytes",
        "confirm",
    ]: getattr(_get(_k), _m)(**_pick(d, _p)),
    # -- UsbEjectManager --
    "storagectl_usb_list_removable_drives": lambda d, _k="usb", _m="list_removable_drives", _p=[]: getattr(
        _get(_k), _m
    )(**_pick(d, _p)),
    "storagectl_usb_get_drive_info": lambda d, _k="usb", _m="get_drive_info", _p=["drive_letter"]: getattr(
        _get(_k), _m
    )(**_pick(d, _p)),
    "storagectl_usb_eject_drive": lambda d, _k="usb", _m="eject_drive", _p=["drive_letter", "confirm"]: getattr(
        _get(_k), _m
    )(**_pick(d, _p)),
}
