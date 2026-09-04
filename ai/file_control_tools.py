"""File Control tool registry
=============================
Wires system_control/files/* (encryption, permissions, sharing, sync,
backup, recovery, filename indexing, hidden-file control, file-type
associations) into the AI tool-calling loop. Same pattern as
ai/system_config_tools.py and ai/process_control_tools.py: lazy
singletons + a flat FILE_CONTROL_TOOLS / FILE_CONTROL_DIRECT_HANDLERS
pair, merged at the bottom of ai/tools_schema.py and ai/tool_runtime.py
respectively (see the two-line imports there).

Naming: every tool is prefixed `filectl_` to avoid colliding with the
existing `files_*`/file-operation tools backed by the top-level files/
package (files/manager, files/pdf, files/office, files/compression,
files/search - see windows/__init__.py) - those stay focused on
everyday open/move/convert/search operations; these are the deeper,
often-destructive control surface (encryption, ACLs, network shares,
sync, backup/recovery).

Every write/encrypt/decrypt/grant/remove/share/unshare/sync/backup/
delete/restore method on the underlying classes is confirm-gated
(confirm: bool, defaults False) - same pattern as every other
destructive tool in this codebase.
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

    if key == "encryption":
        from system_control.files.encryption import FileEncryption

        obj = FileEncryption()
    elif key == "permissions":
        from system_control.files.permissions import FilePermissions

        obj = FilePermissions()
    elif key == "sharing":
        from system_control.files.sharing import FileSharing

        obj = FileSharing()
    elif key == "sync":
        from system_control.files.sync import FileSync

        obj = FileSync()
    elif key == "backup":
        from system_control.files.backup import FileBackup

        obj = FileBackup()
    elif key == "recovery":
        from system_control.files.recovery import FileRecovery

        obj = FileRecovery()
    elif key == "indexing":
        from system_control.files.indexing import FileIndexer

        obj = FileIndexer()
    elif key == "hidden_files":
        from system_control.files.hidden_files import HiddenFiles

        obj = HiddenFiles()
    elif key == "file_associations":
        from system_control.files.file_associations import FileAssociations

        obj = FileAssociations()
    else:
        raise KeyError(f"Unknown file_control tool key: {key}")

    _instances[key] = obj
    return obj


_RIGHTS_ENUM = ["read", "write", "modify", "full", "read_execute"]

# ---------------------------------------------------------------------------
# Tool schemas
# ---------------------------------------------------------------------------
FILE_CONTROL_TOOLS = [
    # -- FileEncryption --
    _tool(
        "filectl_encrypt_file",
        "Encrypt a file in place (or to output_path) using ULTRON's shared at-rest encryption " "key. Confirm-gated.",
        {"path": {"type": "string"}, "output_path": {"type": "string"}, "confirm": {"type": "boolean"}},
        ["path"],
    ),
    _tool(
        "filectl_decrypt_file",
        "Decrypt a file previously encrypted by filectl_encrypt_file, in place or to output_path. " "Confirm-gated.",
        {"path": {"type": "string"}, "output_path": {"type": "string"}, "confirm": {"type": "boolean"}},
        ["path"],
    ),
    _tool(
        "filectl_is_file_encrypted",
        "Check whether a file was encrypted by ULTRON's file-encryption tool.",
        {"path": {"type": "string"}},
        ["path"],
    ),
    # -- FilePermissions --
    _tool(
        "filectl_get_permissions",
        "List the current NTFS ACL entries for a file or folder.",
        {"path": {"type": "string"}},
        ["path"],
    ),
    _tool(
        "filectl_set_permission",
        "Grant a user/group a permission level (read/write/modify/full/read_execute) on a file "
        "or folder. Confirm-gated.",
        {
            "path": {"type": "string"},
            "user": {"type": "string"},
            "rights": {"type": "string", "enum": _RIGHTS_ENUM},
            "confirm": {"type": "boolean"},
        },
        ["path", "user", "rights"],
    ),
    _tool(
        "filectl_remove_permission",
        "Remove all explicit ACL entries for a user/group from a file or folder. Confirm-gated.",
        {"path": {"type": "string"}, "user": {"type": "string"}, "confirm": {"type": "boolean"}},
        ["path", "user"],
    ),
    _tool(
        "filectl_take_ownership",
        "Take ownership of a file or folder as the current user. Needs admin for files you "
        "don't own. Confirm-gated.",
        {"path": {"type": "string"}, "recursive": {"type": "boolean"}, "confirm": {"type": "boolean"}},
        ["path"],
    ),
    _tool(
        "filectl_make_read_only",
        "Set the read-only attribute on a file. Confirm-gated.",
        {"path": {"type": "string"}, "confirm": {"type": "boolean"}},
        ["path"],
    ),
    _tool(
        "filectl_remove_read_only",
        "Clear the read-only attribute on a file. Confirm-gated.",
        {"path": {"type": "string"}, "confirm": {"type": "boolean"}},
        ["path"],
    ),
    # -- FileSharing --
    _tool(
        "filectl_list_shares",
        "List all current SMB network shares on this machine.",
    ),
    _tool(
        "filectl_get_share_permissions",
        "Get the access-control entries for one existing network share.",
        {"share_name": {"type": "string"}},
        ["share_name"],
    ),
    _tool(
        "filectl_share_folder",
        "Share a local folder over the network (SMB). Needs admin. Confirm-gated - makes the "
        "folder reachable from other devices on the network.",
        {
            "path": {"type": "string"},
            "share_name": {"type": "string"},
            "read_only": {"type": "boolean"},
            "confirm": {"type": "boolean"},
        },
        ["path", "share_name"],
    ),
    _tool(
        "filectl_unshare_folder",
        "Remove a network share (the folder itself is untouched). Needs admin. Confirm-gated.",
        {"share_name": {"type": "string"}, "confirm": {"type": "boolean"}},
        ["share_name"],
    ),
    # -- FileSync --
    _tool(
        "filectl_preview_sync",
        "Dry-run a folder sync (robocopy /L) to preview what would change without touching " "anything.",
        {"source": {"type": "string"}, "destination": {"type": "string"}, "mirror": {"type": "boolean"}},
        ["source", "destination"],
    ),
    _tool(
        "filectl_sync_folders",
        "Sync source folder to destination. mirror=false copies new/changed files only (nothing "
        "deleted); mirror=true makes destination an exact mirror (deletes extra files in "
        "destination). Confirm-gated.",
        {
            "source": {"type": "string"},
            "destination": {"type": "string"},
            "mirror": {"type": "boolean"},
            "confirm": {"type": "boolean"},
        },
        ["source", "destination"],
    ),
    # -- FileBackup --
    _tool(
        "filectl_backup_path",
        "Back up a file or folder to a timestamped archive under ultron_data/file_backups/ "
        "(folders are zipped). Confirm-gated.",
        {"path": {"type": "string"}, "confirm": {"type": "boolean"}},
        ["path"],
    ),
    _tool(
        "filectl_list_backups",
        "List previously created file/folder backups, optionally filtered by filename substring.",
        {"source_filter": {"type": "string"}},
    ),
    _tool(
        "filectl_delete_backup",
        "Delete a previously created file backup. Confirm-gated.",
        {"backup_path": {"type": "string"}, "confirm": {"type": "boolean"}},
        ["backup_path"],
    ),
    # -- FileRecovery --
    _tool(
        "filectl_restore_from_backup",
        "Restore a file/folder backup (from filectl_backup_path) to a target path. Confirm-gated "
        "- overwrites the target if it exists.",
        {"backup_path": {"type": "string"}, "target_path": {"type": "string"}, "confirm": {"type": "boolean"}},
        ["backup_path", "target_path"],
    ),
    _tool(
        "filectl_list_recycle_bin",
        "List items currently in the Recycle Bin (name, original path, size).",
    ),
    _tool(
        "filectl_restore_from_recycle_bin",
        "Restore an item from the Recycle Bin back to its original location, matched by name. "
        "Confirm-gated, best-effort.",
        {"item_name": {"type": "string"}, "confirm": {"type": "boolean"}},
        ["item_name"],
    ),
    # -- FileIndexer --
    _tool(
        "filectl_build_index",
        "Crawl a folder and (re)build ULTRON's local filename index for instant search later, "
        "optionally filtered to specific extensions. Confirm-gated - can be slow on large roots.",
        {
            "root": {"type": "string"},
            "extensions": {"type": "array", "items": {"type": "string"}},
            "confirm": {"type": "boolean"},
        },
        ["root"],
    ),
    _tool(
        "filectl_search_index",
        "Search the local filename index by substring, optionally filtered by extension.",
        {"query": {"type": "string"}, "extension": {"type": "string"}, "limit": {"type": "integer"}},
        ["query"],
    ),
    _tool(
        "filectl_get_index_stats",
        "Get total indexed file count and per-root build info for the local filename index.",
    ),
    _tool(
        "filectl_remove_index_root",
        "Remove one root's entries from the filename index (index only - files on disk are "
        "untouched). Confirm-gated.",
        {"root": {"type": "string"}, "confirm": {"type": "boolean"}},
        ["root"],
    ),
    _tool(
        "filectl_clear_index",
        "Wipe the entire filename index (every indexed root). Confirm-gated.",
        {"confirm": {"type": "boolean"}},
    ),
    # -- HiddenFiles --
    _tool(
        "filectl_is_hidden",
        "Check whether a file/folder currently has the hidden attribute set.",
        {"path": {"type": "string"}},
        ["path"],
    ),
    _tool(
        "filectl_list_hidden",
        "List hidden files/folders directly inside a folder (non-recursive).",
        {"folder": {"type": "string"}},
        ["folder"],
    ),
    _tool(
        "filectl_hide_file",
        "Set the hidden attribute on a file/folder. Confirm-gated.",
        {"path": {"type": "string"}, "confirm": {"type": "boolean"}},
        ["path"],
    ),
    _tool(
        "filectl_unhide_file",
        "Clear the hidden (and system) attribute on a file/folder. Confirm-gated.",
        {"path": {"type": "string"}, "confirm": {"type": "boolean"}},
        ["path"],
    ),
    _tool(
        "filectl_hide_and_protect_file",
        "Set hidden AND system attributes on a file/folder - stays invisible even with 'show "
        "hidden files' turned on. Confirm-gated.",
        {"path": {"type": "string"}, "confirm": {"type": "boolean"}},
        ["path"],
    ),
    _tool(
        "filectl_get_explorer_hidden_setting",
        "Read Explorer's current 'show hidden files' and 'show protected OS files' settings.",
    ),
    _tool(
        "filectl_set_explorer_hidden_setting",
        "Toggle whether Explorer shows hidden files/folders at all. Confirm-gated.",
        {"show_hidden": {"type": "boolean"}, "confirm": {"type": "boolean"}},
        ["show_hidden"],
    ),
    # -- FileAssociations --
    _tool(
        "filectl_get_default_app",
        "Look up the program currently associated with a file extension (e.g. '.pdf').",
        {"extension": {"type": "string"}},
        ["extension"],
    ),
    _tool(
        "filectl_list_associations",
        "Batch lookup of the default program for several file extensions at once.",
        {"extensions": {"type": "array", "items": {"type": "string"}}},
        ["extensions"],
    ),
    _tool(
        "filectl_set_default_app",
        "Associate a file extension with a ProgId (and optionally an exe path). May not "
        "override an existing user choice on modern Windows - see result caveat. Confirm-gated.",
        {
            "extension": {"type": "string"},
            "prog_id": {"type": "string"},
            "exe_path": {"type": "string"},
            "confirm": {"type": "boolean"},
        },
        ["extension", "prog_id"],
    ),
    _tool(
        "filectl_reset_association",
        "Remove the custom association for a file extension, reverting to the system default. " "Confirm-gated.",
        {"extension": {"type": "string"}, "confirm": {"type": "boolean"}},
        ["extension"],
    ),
    _tool(
        "filectl_open_with_dialog",
        "Open the native Windows 'Open with' picker for a specific file - the reliable way to "
        "change its default app. Not confirm-gated, only opens a picker UI.",
        {"path": {"type": "string"}},
        ["path"],
    ),
]

# ---------------------------------------------------------------------------
# Direct handlers - flat name -> lambda(args_dict) -> result dict
# ---------------------------------------------------------------------------
FILE_CONTROL_DIRECT_HANDLERS = {
    # -- FileEncryption --
    "filectl_encrypt_file": lambda d, _k="encryption", _m="encrypt_file", _p=[
        "path",
        "output_path",
        "confirm",
    ]: getattr(_get(_k), _m)(**_pick(d, _p)),
    "filectl_decrypt_file": lambda d, _k="encryption", _m="decrypt_file", _p=[
        "path",
        "output_path",
        "confirm",
    ]: getattr(_get(_k), _m)(**_pick(d, _p)),
    "filectl_is_file_encrypted": lambda d, _k="encryption", _m="is_file_encrypted", _p=["path"]: getattr(_get(_k), _m)(
        **_pick(d, _p)
    ),
    # -- FilePermissions --
    "filectl_get_permissions": lambda d, _k="permissions", _m="get_permissions", _p=["path"]: getattr(_get(_k), _m)(
        **_pick(d, _p)
    ),
    "filectl_set_permission": lambda d, _k="permissions", _m="set_permission", _p=[
        "path",
        "user",
        "rights",
        "confirm",
    ]: getattr(_get(_k), _m)(**_pick(d, _p)),
    "filectl_remove_permission": lambda d, _k="permissions", _m="remove_permission", _p=[
        "path",
        "user",
        "confirm",
    ]: getattr(_get(_k), _m)(**_pick(d, _p)),
    "filectl_take_ownership": lambda d, _k="permissions", _m="take_ownership", _p=[
        "path",
        "recursive",
        "confirm",
    ]: getattr(_get(_k), _m)(**_pick(d, _p)),
    "filectl_make_read_only": lambda d, _k="permissions", _m="make_read_only", _p=["path", "confirm"]: getattr(
        _get(_k), _m
    )(**_pick(d, _p)),
    "filectl_remove_read_only": lambda d, _k="permissions", _m="remove_read_only", _p=["path", "confirm"]: getattr(
        _get(_k), _m
    )(**_pick(d, _p)),
    # -- FileSharing --
    "filectl_list_shares": lambda d, _k="sharing", _m="list_shares", _p=[]: getattr(_get(_k), _m)(**_pick(d, _p)),
    "filectl_get_share_permissions": lambda d, _k="sharing", _m="get_share_permissions", _p=["share_name"]: getattr(
        _get(_k), _m
    )(**_pick(d, _p)),
    "filectl_share_folder": lambda d, _k="sharing", _m="share_folder", _p=[
        "path",
        "share_name",
        "read_only",
        "confirm",
    ]: getattr(_get(_k), _m)(**_pick(d, _p)),
    "filectl_unshare_folder": lambda d, _k="sharing", _m="unshare_folder", _p=["share_name", "confirm"]: getattr(
        _get(_k), _m
    )(**_pick(d, _p)),
    # -- FileSync --
    "filectl_preview_sync": lambda d, _k="sync", _m="preview_sync", _p=["source", "destination", "mirror"]: getattr(
        _get(_k), _m
    )(**_pick(d, _p)),
    "filectl_sync_folders": lambda d, _k="sync", _m="sync_folders", _p=[
        "source",
        "destination",
        "mirror",
        "confirm",
    ]: getattr(_get(_k), _m)(**_pick(d, _p)),
    # -- FileBackup --
    "filectl_backup_path": lambda d, _k="backup", _m="backup_path", _p=["path", "confirm"]: getattr(_get(_k), _m)(
        **_pick(d, _p)
    ),
    "filectl_list_backups": lambda d, _k="backup", _m="list_backups", _p=["source_filter"]: getattr(_get(_k), _m)(
        **_pick(d, _p)
    ),
    "filectl_delete_backup": lambda d, _k="backup", _m="delete_backup", _p=["backup_path", "confirm"]: getattr(
        _get(_k), _m
    )(**_pick(d, _p)),
    # -- FileRecovery --
    "filectl_restore_from_backup": lambda d, _k="recovery", _m="restore_from_backup", _p=[
        "backup_path",
        "target_path",
        "confirm",
    ]: getattr(_get(_k), _m)(**_pick(d, _p)),
    "filectl_list_recycle_bin": lambda d, _k="recovery", _m="list_recycle_bin", _p=[]: getattr(_get(_k), _m)(
        **_pick(d, _p)
    ),
    "filectl_restore_from_recycle_bin": lambda d, _k="recovery", _m="restore_from_recycle_bin", _p=[
        "item_name",
        "confirm",
    ]: getattr(_get(_k), _m)(**_pick(d, _p)),
    # -- FileIndexer --
    "filectl_build_index": lambda d, _k="indexing", _m="build_index", _p=["root", "extensions", "confirm"]: getattr(
        _get(_k), _m
    )(**_pick(d, _p)),
    "filectl_search_index": lambda d, _k="indexing", _m="search_index", _p=["query", "extension", "limit"]: getattr(
        _get(_k), _m
    )(**_pick(d, _p)),
    "filectl_get_index_stats": lambda d, _k="indexing", _m="get_index_stats", _p=[]: getattr(_get(_k), _m)(
        **_pick(d, _p)
    ),
    "filectl_remove_index_root": lambda d, _k="indexing", _m="remove_root", _p=["root", "confirm"]: getattr(
        _get(_k), _m
    )(**_pick(d, _p)),
    "filectl_clear_index": lambda d, _k="indexing", _m="clear_index", _p=["confirm"]: getattr(_get(_k), _m)(
        **_pick(d, _p)
    ),
    # -- HiddenFiles --
    "filectl_is_hidden": lambda d, _k="hidden_files", _m="is_hidden", _p=["path"]: getattr(_get(_k), _m)(
        **_pick(d, _p)
    ),
    "filectl_list_hidden": lambda d, _k="hidden_files", _m="list_hidden", _p=["folder"]: getattr(_get(_k), _m)(
        **_pick(d, _p)
    ),
    "filectl_hide_file": lambda d, _k="hidden_files", _m="hide", _p=["path", "confirm"]: getattr(_get(_k), _m)(
        **_pick(d, _p)
    ),
    "filectl_unhide_file": lambda d, _k="hidden_files", _m="unhide", _p=["path", "confirm"]: getattr(_get(_k), _m)(
        **_pick(d, _p)
    ),
    "filectl_hide_and_protect_file": lambda d, _k="hidden_files", _m="hide_and_protect", _p=[
        "path",
        "confirm",
    ]: getattr(_get(_k), _m)(**_pick(d, _p)),
    "filectl_get_explorer_hidden_setting": lambda d, _k="hidden_files", _m="get_explorer_hidden_setting", _p=[]: getattr(
        _get(_k), _m
    )(
        **_pick(d, _p)
    ),
    "filectl_set_explorer_hidden_setting": lambda d, _k="hidden_files", _m="set_explorer_hidden_setting", _p=[
        "show_hidden",
        "confirm",
    ]: getattr(_get(_k), _m)(**_pick(d, _p)),
    # -- FileAssociations --
    "filectl_get_default_app": lambda d, _k="file_associations", _m="get_default_app", _p=["extension"]: getattr(
        _get(_k), _m
    )(**_pick(d, _p)),
    "filectl_list_associations": lambda d, _k="file_associations", _m="list_associations", _p=["extensions"]: getattr(
        _get(_k), _m
    )(**_pick(d, _p)),
    "filectl_set_default_app": lambda d, _k="file_associations", _m="set_default_app", _p=[
        "extension",
        "prog_id",
        "exe_path",
        "confirm",
    ]: getattr(_get(_k), _m)(**_pick(d, _p)),
    "filectl_reset_association": lambda d, _k="file_associations", _m="reset_association", _p=[
        "extension",
        "confirm",
    ]: getattr(_get(_k), _m)(**_pick(d, _p)),
    "filectl_open_with_dialog": lambda d, _k="file_associations", _m="open_with_dialog", _p=["path"]: getattr(
        _get(_k), _m
    )(**_pick(d, _p)),
}
