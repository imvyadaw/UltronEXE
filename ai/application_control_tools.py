"""Application Control tool registry
=====================================
Wires system_control/applications/* (installed-application lifecycle:
package discovery/install, uninstall, updates, per-app compatibility
settings, appdata backup, and cache cleanup) into the AI tool-calling
loop. Same pattern as ai/storage_control_tools.py and ai/security_
control_tools.py: lazy singletons + a flat APPLICATION_CONTROL_TOOLS /
APPLICATION_CONTROL_DIRECT_HANDLERS pair, merged at the bottom of
ai/tools_schema.py and ai/tool_runtime.py respectively.

Naming: every tool is prefixed `appctl_`, one segment per underlying
module - `appctl_pkg_*` (package_manager.py), `appctl_uninstall_*`
(app_uninstaller.py), `appctl_update_*` (app_updater.py),
`appctl_settings_*` (app_settings.py), `appctl_data_*`
(app_data_backup.py), `appctl_cache_*` (app_cache.py),
`appctl_defaults_*` (default_apps.py), `appctl_exec_*`
(app_permissions.py - execution allow/blocklist, not to be confused
with security/app_permissions.py's privacy-capability tools),
`appctl_browser_*` (browser_control.py), `appctl_office_*`
(office_control.py), `appctl_media_*` (media_control.py),
`appctl_comm_*` (communication_control.py).

Most state-changing methods here are confirm-gated because they
install/remove software, run vendor installers, overwrite app data, or
delete cache/leftover files outright - this mirrors the underlying
classes' own confirm-gating choices rather than gating everything
uniformly.
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

    if key == "pkg":
        from system_control.applications.package_manager import PackageManager

        obj = PackageManager()
    elif key == "uninstall":
        from system_control.applications.app_uninstaller import AppUninstaller

        obj = AppUninstaller()
    elif key == "update":
        from system_control.applications.app_updater import AppUpdater

        obj = AppUpdater()
    elif key == "settings":
        from system_control.applications.app_settings import AppAdvancedSettings

        obj = AppAdvancedSettings()
    elif key == "data":
        from system_control.applications.app_data_backup import AppDataBackup

        obj = AppDataBackup()
    elif key == "cache":
        from system_control.applications.app_cache import AppCacheManager

        obj = AppCacheManager()
    elif key == "defaults":
        from system_control.applications.default_apps import DefaultAppsManager

        obj = DefaultAppsManager()
    elif key == "exec":
        from system_control.applications.app_permissions import AppExecutionPolicy

        obj = AppExecutionPolicy()
    elif key == "browser":
        from system_control.applications.browser_control import BrowserControl

        obj = BrowserControl()
    elif key == "office":
        from system_control.applications.office_control import OfficeControl

        obj = OfficeControl()
    elif key == "media":
        from system_control.applications.media_control import MediaControl

        obj = MediaControl()
    elif key == "comm":
        from system_control.applications.communication_control import CommunicationControl

        obj = CommunicationControl()
    else:
        raise KeyError(f"Unknown application_control tool key: {key}")

    _instances[key] = obj
    return obj


# ---------------------------------------------------------------------------
# Tool schemas
# ---------------------------------------------------------------------------
APPLICATION_CONTROL_TOOLS = [
    # -- PackageManager --
    _tool(
        "appctl_pkg_list_installed",
        "List every installed Win32 program (from the registry Uninstall hive) and, optionally, UWP/Store packages.",
        {"include_appx": {"type": "boolean"}},
    ),
    _tool(
        "appctl_pkg_get_info",
        "Look up an installed Win32 app by (partial) display name.",
        {"name": {"type": "string"}},
        ["name"],
    ),
    _tool(
        "appctl_pkg_search",
        "Search the winget catalog for installable packages by name.",
        {"query": {"type": "string"}},
        ["query"],
    ),
    _tool(
        "appctl_pkg_list_sources",
        "List configured winget package sources.",
    ),
    _tool(
        "appctl_pkg_install",
        "Install a package by its winget package Id. Confirm-gated.",
        {"package_id": {"type": "string"}, "confirm": {"type": "boolean"}},
        ["package_id"],
    ),
    # -- AppUninstaller --
    _tool(
        "appctl_uninstall_get_command",
        "Look up how a Win32 app would be uninstalled (its registered uninstall string), without running anything.",
        {"app_name": {"type": "string"}},
        ["app_name"],
    ),
    _tool(
        "appctl_uninstall_app",
        "Uninstall a Win32 app via winget (preferred) or its registered UninstallString. Confirm-gated.",
        {"app_name": {"type": "string"}, "confirm": {"type": "boolean"}},
        ["app_name"],
    ),
    _tool(
        "appctl_uninstall_list_appx",
        "List installed UWP/Store packages, optionally filtered by name.",
        {"name_filter": {"type": "string"}},
    ),
    _tool(
        "appctl_uninstall_appx",
        "Remove a UWP/Store app by its PackageFullName. Confirm-gated.",
        {"package_full_name": {"type": "string"}, "confirm": {"type": "boolean"}},
        ["package_full_name"],
    ),
    _tool(
        "appctl_uninstall_scan_leftovers",
        "Scan common install locations for leftover files/folders matching an app name after uninstalling. Read-only.",
        {"app_name": {"type": "string"}},
        ["app_name"],
    ),
    _tool(
        "appctl_uninstall_force_remove_leftovers",
        "Permanently delete specific leftover paths reported by appctl_uninstall_scan_leftovers. Confirm-gated, destructive.",
        {"paths": {"type": "array", "items": {"type": "string"}}, "confirm": {"type": "boolean"}},
        ["paths"],
    ),
    # -- AppUpdater --
    _tool(
        "appctl_update_list_available",
        "List every installed package winget reports a newer version for.",
    ),
    _tool(
        "appctl_update_check",
        "Check whether one specific package (by winget Id) has an update available.",
        {"package_id": {"type": "string"}},
        ["package_id"],
    ),
    _tool(
        "appctl_update_app",
        "Upgrade one package to its latest version via winget. Confirm-gated.",
        {"package_id": {"type": "string"}, "confirm": {"type": "boolean"}},
        ["package_id"],
    ),
    _tool(
        "appctl_update_all",
        "Upgrade every package winget reports an update for. Confirm-gated.",
        {"confirm": {"type": "boolean"}},
    ),
    _tool(
        "appctl_update_sources",
        "Refresh winget's local package source indexes.",
    ),
    # -- AppAdvancedSettings --
    _tool(
        "appctl_settings_get_compat_flags",
        "Read the current AppCompatFlags Layers string set for an exe (e.g. RUNASADMIN, HIGHDPIAWARE).",
        {"exe_path": {"type": "string"}},
        ["exe_path"],
    ),
    _tool(
        "appctl_settings_set_run_as_admin",
        "Toggle 'Run this program as an administrator' for one exe. Confirm-gated.",
        {"exe_path": {"type": "string"}, "enabled": {"type": "boolean"}, "confirm": {"type": "boolean"}},
        ["exe_path", "enabled"],
    ),
    _tool(
        "appctl_settings_list_execution_aliases",
        "List Store-app execution aliases (command names claimed in PATH) and whether each is enabled.",
    ),
    _tool(
        "appctl_settings_set_execution_alias",
        "Enable/disable one app execution alias by name. Confirm-gated.",
        {"alias_name": {"type": "string"}, "enabled": {"type": "boolean"}, "confirm": {"type": "boolean"}},
        ["alias_name", "enabled"],
    ),
    _tool(
        "appctl_settings_reset_app",
        "Reset a UWP/Store app's local state to default, without uninstalling it. Confirm-gated, destructive.",
        {"package_family_name": {"type": "string"}, "confirm": {"type": "boolean"}},
        ["package_family_name"],
    ),
    # -- AppDataBackup --
    _tool(
        "appctl_data_discover",
        "Find every AppData folder matching an app name across LocalAppData/Roaming/LocalLow.",
        {"app_name": {"type": "string"}},
        ["app_name"],
    ),
    _tool(
        "appctl_data_backup",
        "Zip up all discovered AppData folders for an app into a single archive. Confirm-gated.",
        {"app_name": {"type": "string"}, "destination_path": {"type": "string"}, "confirm": {"type": "boolean"}},
        ["app_name", "destination_path"],
    ),
    _tool(
        "appctl_data_list_backups",
        "List app-data-backup archives in a folder, with the app name and creation time each was made for.",
        {"backup_dir": {"type": "string"}},
        ["backup_dir"],
    ),
    _tool(
        "appctl_data_restore",
        "Restore an app-data-backup archive, overwriting current contents at the original paths. Confirm-gated, destructive.",
        {"backup_path": {"type": "string"}, "confirm": {"type": "boolean"}},
        ["backup_path"],
    ),
    # -- AppCacheManager --
    _tool(
        "appctl_cache_get_size",
        "Find cache/temp folders for an app and report their combined size, without deleting anything.",
        {"app_name": {"type": "string"}},
        ["app_name"],
    ),
    _tool(
        "appctl_cache_clear",
        "Delete every cache-named folder and matching temp entry found for an app. Confirm-gated, destructive.",
        {"app_name": {"type": "string"}, "confirm": {"type": "boolean"}},
        ["app_name"],
    ),
    _tool(
        "appctl_cache_clear_store",
        "Reset the Microsoft Store app's own cache via wsreset.exe. Confirm-gated.",
        {"confirm": {"type": "boolean"}},
    ),
    # -- DefaultAppsManager --
    _tool(
        "appctl_defaults_get_for_class",
        "Read the current default app's ProgId for a common class: 'browser', 'browser_https', or 'mail'.",
        {"app_class": {"type": "string"}},
        ["app_class"],
    ),
    _tool(
        "appctl_defaults_export",
        "Export the whole current default-app association profile to an XML file via DISM.",
        {"destination_path": {"type": "string"}},
        ["destination_path"],
    ),
    _tool(
        "appctl_defaults_import",
        "Apply a default-app association XML machine-wide via DISM. Confirm-gated, admin-required.",
        {"source_path": {"type": "string"}, "confirm": {"type": "boolean"}},
        ["source_path"],
    ),
    _tool(
        "appctl_defaults_open_settings",
        "Open Settings > Default apps, optionally deep-linked to a specific app class.",
        {"app_class": {"type": "string"}},
    ),
    # -- AppExecutionPolicy --
    _tool(
        "appctl_exec_is_restricted",
        "Read whether app-execution restriction (DisallowRun) enforcement is currently on for this user.",
    ),
    _tool(
        "appctl_exec_set_restricted",
        "Toggle app-execution restriction enforcement on/off for this user. Confirm-gated.",
        {"enabled": {"type": "boolean"}, "confirm": {"type": "boolean"}},
        ["enabled"],
    ),
    _tool(
        "appctl_exec_list_blocked",
        "List every exe name currently blocked from launching (DisallowRun list).",
    ),
    _tool(
        "appctl_exec_block",
        "Block an exe name from being launched via Explorer/Start/Run. Confirm-gated.",
        {"exe_name": {"type": "string"}, "confirm": {"type": "boolean"}},
        ["exe_name"],
    ),
    _tool(
        "appctl_exec_allow",
        "Remove the execution block on an exe name, allowing it to launch again. Confirm-gated.",
        {"exe_name": {"type": "string"}, "confirm": {"type": "boolean"}},
        ["exe_name"],
    ),
    # -- BrowserControl --
    _tool(
        "appctl_browser_list_installed",
        "List every browser registered under StartMenuInternet (Settings > Default apps > Web browser source list).",
    ),
    _tool(
        "appctl_browser_get_default",
        "Read the current default browser's ProgId.",
    ),
    _tool(
        "appctl_browser_open_settings",
        "Open Settings > Default apps > Web browser.",
    ),
    _tool(
        "appctl_browser_close_all",
        "Force-close every running browser process (Chrome, Edge, Firefox, Brave, Opera, IE). Confirm-gated.",
        {"confirm": {"type": "boolean"}},
    ),
    _tool(
        "appctl_browser_clear_all_cache",
        "Delete the disk cache (not history/passwords) for every installed Chromium-family browser. Confirm-gated, destructive.",
        {"confirm": {"type": "boolean"}},
    ),
    # -- OfficeControl --
    _tool(
        "appctl_office_get_install_info",
        "Read Office Click-to-Run version, platform, install path, and update channel.",
    ),
    _tool(
        "appctl_office_list_installed_apps",
        "List which individual Office apps (Word, Excel, PowerPoint, Outlook, Access, OneNote, Teams) have a resolvable exe on this machine.",
    ),
    _tool(
        "appctl_office_set_update_channel",
        "Switch Office's update channel (current, monthly_enterprise, semi_annual, semi_annual_preview, beta) and check for updates now. Confirm-gated, admin-required.",
        {"channel": {"type": "string"}, "confirm": {"type": "boolean"}},
        ["channel"],
    ),
    _tool(
        "appctl_office_close_all",
        "Force-close every running Office app. Confirm-gated - unsaved changes are lost.",
        {"confirm": {"type": "boolean"}},
    ),
    # -- MediaControl --
    _tool(
        "appctl_media_play_pause",
        "Toggle play/pause on whichever app owns the current OS media session.",
    ),
    _tool(
        "appctl_media_stop",
        "Send the media-stop key to the current media session.",
    ),
    _tool(
        "appctl_media_next_track",
        "Send the next-track key to the current media session.",
    ),
    _tool(
        "appctl_media_previous_track",
        "Send the previous-track key to the current media session.",
    ),
    _tool(
        "appctl_media_set_mute",
        "Toggle system volume mute.",
        {"muted": {"type": "boolean"}},
    ),
    _tool(
        "appctl_media_volume_up",
        "Increase system volume by one or more steps.",
        {"steps": {"type": "integer"}},
    ),
    _tool(
        "appctl_media_volume_down",
        "Decrease system volume by one or more steps.",
        {"steps": {"type": "integer"}},
    ),
    _tool(
        "appctl_media_get_now_playing",
        "Best-effort read of the current media session's title/artist/app (requires optional 'winsdk' package).",
    ),
    # -- CommunicationControl --
    _tool(
        "appctl_comm_list_installed",
        "List which known communication apps (WhatsApp, Telegram, Discord, Slack, Signal, Skype, Messenger, Teams, Zoom) are installed.",
    ),
    _tool(
        "appctl_comm_get_startup_status",
        "For each known communication app, report whether it auto-launches at sign-in.",
    ),
    _tool(
        "appctl_comm_close_all",
        "Force-close every running communication app. Confirm-gated.",
        {"confirm": {"type": "boolean"}},
    ),
]

# ---------------------------------------------------------------------------
# Direct handlers - flat name -> lambda(args_dict) -> result dict
# ---------------------------------------------------------------------------
APPLICATION_CONTROL_DIRECT_HANDLERS = {
    # -- PackageManager --
    "appctl_pkg_list_installed": lambda d, _k="pkg", _m="list_installed_packages", _p=["include_appx"]: getattr(
        _get(_k), _m
    )(**_pick(d, _p)),
    "appctl_pkg_get_info": lambda d, _k="pkg", _m="get_package_info", _p=["name"]: getattr(_get(_k), _m)(
        **_pick(d, _p)
    ),
    "appctl_pkg_search": lambda d, _k="pkg", _m="search_available", _p=["query"]: getattr(_get(_k), _m)(**_pick(d, _p)),
    "appctl_pkg_list_sources": lambda d, _k="pkg", _m="list_winget_sources", _p=[]: getattr(_get(_k), _m)(
        **_pick(d, _p)
    ),
    "appctl_pkg_install": lambda d, _k="pkg", _m="install_package", _p=["package_id", "confirm"]: getattr(_get(_k), _m)(
        **_pick(d, _p)
    ),
    # -- AppUninstaller --
    "appctl_uninstall_get_command": lambda d, _k="uninstall", _m="get_uninstall_command", _p=["app_name"]: getattr(
        _get(_k), _m
    )(**_pick(d, _p)),
    "appctl_uninstall_app": lambda d, _k="uninstall", _m="uninstall_app", _p=["app_name", "confirm"]: getattr(
        _get(_k), _m
    )(**_pick(d, _p)),
    "appctl_uninstall_list_appx": lambda d, _k="uninstall", _m="list_appx_packages", _p=["name_filter"]: getattr(
        _get(_k), _m
    )(**_pick(d, _p)),
    "appctl_uninstall_appx": lambda d, _k="uninstall", _m="uninstall_appx_package", _p=[
        "package_full_name",
        "confirm",
    ]: getattr(_get(_k), _m)(**_pick(d, _p)),
    "appctl_uninstall_scan_leftovers": lambda d, _k="uninstall", _m="scan_leftovers", _p=["app_name"]: getattr(
        _get(_k), _m
    )(**_pick(d, _p)),
    "appctl_uninstall_force_remove_leftovers": lambda d, _k="uninstall", _m="force_remove_leftovers", _p=[
        "paths",
        "confirm",
    ]: getattr(_get(_k), _m)(**_pick(d, _p)),
    # -- AppUpdater --
    "appctl_update_list_available": lambda d, _k="update", _m="list_available_updates", _p=[]: getattr(_get(_k), _m)(
        **_pick(d, _p)
    ),
    "appctl_update_check": lambda d, _k="update", _m="check_app_update", _p=["package_id"]: getattr(_get(_k), _m)(
        **_pick(d, _p)
    ),
    "appctl_update_app": lambda d, _k="update", _m="update_app", _p=["package_id", "confirm"]: getattr(_get(_k), _m)(
        **_pick(d, _p)
    ),
    "appctl_update_all": lambda d, _k="update", _m="update_all", _p=["confirm"]: getattr(_get(_k), _m)(**_pick(d, _p)),
    "appctl_update_sources": lambda d, _k="update", _m="update_sources", _p=[]: getattr(_get(_k), _m)(**_pick(d, _p)),
    # -- AppAdvancedSettings --
    "appctl_settings_get_compat_flags": lambda d, _k="settings", _m="get_compat_flags", _p=["exe_path"]: getattr(
        _get(_k), _m
    )(**_pick(d, _p)),
    "appctl_settings_set_run_as_admin": lambda d, _k="settings", _m="set_run_as_administrator", _p=[
        "exe_path",
        "enabled",
        "confirm",
    ]: getattr(_get(_k), _m)(**_pick(d, _p)),
    "appctl_settings_list_execution_aliases": lambda d, _k="settings", _m="list_app_execution_aliases", _p=[]: getattr(
        _get(_k), _m
    )(**_pick(d, _p)),
    "appctl_settings_set_execution_alias": lambda d, _k="settings", _m="set_app_execution_alias", _p=[
        "alias_name",
        "enabled",
        "confirm",
    ]: getattr(_get(_k), _m)(**_pick(d, _p)),
    "appctl_settings_reset_app": lambda d, _k="settings", _m="reset_app", _p=[
        "package_family_name",
        "confirm",
    ]: getattr(_get(_k), _m)(**_pick(d, _p)),
    # -- AppDataBackup --
    "appctl_data_discover": lambda d, _k="data", _m="discover_app_data_paths", _p=["app_name"]: getattr(_get(_k), _m)(
        **_pick(d, _p)
    ),
    "appctl_data_backup": lambda d, _k="data", _m="backup_app_data", _p=[
        "app_name",
        "destination_path",
        "confirm",
    ]: getattr(_get(_k), _m)(**_pick(d, _p)),
    "appctl_data_list_backups": lambda d, _k="data", _m="list_backups", _p=["backup_dir"]: getattr(_get(_k), _m)(
        **_pick(d, _p)
    ),
    "appctl_data_restore": lambda d, _k="data", _m="restore_app_data", _p=["backup_path", "confirm"]: getattr(
        _get(_k), _m
    )(**_pick(d, _p)),
    # -- AppCacheManager --
    "appctl_cache_get_size": lambda d, _k="cache", _m="get_cache_size", _p=["app_name"]: getattr(_get(_k), _m)(
        **_pick(d, _p)
    ),
    "appctl_cache_clear": lambda d, _k="cache", _m="clear_app_cache", _p=["app_name", "confirm"]: getattr(_get(_k), _m)(
        **_pick(d, _p)
    ),
    "appctl_cache_clear_store": lambda d, _k="cache", _m="clear_windows_store_cache", _p=["confirm"]: getattr(
        _get(_k), _m
    )(**_pick(d, _p)),
    # -- DefaultAppsManager --
    "appctl_defaults_get_for_class": lambda d, _k="defaults", _m="get_default_for_class", _p=["app_class"]: getattr(
        _get(_k), _m
    )(**_pick(d, _p)),
    "appctl_defaults_export": lambda d, _k="defaults", _m="export_default_apps", _p=["destination_path"]: getattr(
        _get(_k), _m
    )(**_pick(d, _p)),
    "appctl_defaults_import": lambda d, _k="defaults", _m="import_default_apps", _p=["source_path", "confirm"]: getattr(
        _get(_k), _m
    )(**_pick(d, _p)),
    "appctl_defaults_open_settings": lambda d, _k="defaults", _m="open_default_apps_settings", _p=[
        "app_class"
    ]: getattr(_get(_k), _m)(**_pick(d, _p)),
    # -- AppExecutionPolicy --
    "appctl_exec_is_restricted": lambda d, _k="exec", _m="is_execution_restriction_enabled", _p=[]: getattr(
        _get(_k), _m
    )(**_pick(d, _p)),
    "appctl_exec_set_restricted": lambda d, _k="exec", _m="set_execution_restriction_enabled", _p=[
        "enabled",
        "confirm",
    ]: getattr(_get(_k), _m)(**_pick(d, _p)),
    "appctl_exec_list_blocked": lambda d, _k="exec", _m="list_blocked_apps", _p=[]: getattr(_get(_k), _m)(
        **_pick(d, _p)
    ),
    "appctl_exec_block": lambda d, _k="exec", _m="block_app_execution", _p=["exe_name", "confirm"]: getattr(
        _get(_k), _m
    )(**_pick(d, _p)),
    "appctl_exec_allow": lambda d, _k="exec", _m="allow_app_execution", _p=["exe_name", "confirm"]: getattr(
        _get(_k), _m
    )(**_pick(d, _p)),
    # -- BrowserControl --
    "appctl_browser_list_installed": lambda d, _k="browser", _m="list_installed_browsers", _p=[]: getattr(_get(_k), _m)(
        **_pick(d, _p)
    ),
    "appctl_browser_get_default": lambda d, _k="browser", _m="get_default_browser", _p=[]: getattr(_get(_k), _m)(
        **_pick(d, _p)
    ),
    "appctl_browser_open_settings": lambda d, _k="browser", _m="open_browser_settings", _p=[]: getattr(_get(_k), _m)(
        **_pick(d, _p)
    ),
    "appctl_browser_close_all": lambda d, _k="browser", _m="close_all_browsers", _p=["confirm"]: getattr(_get(_k), _m)(
        **_pick(d, _p)
    ),
    "appctl_browser_clear_all_cache": lambda d, _k="browser", _m="clear_all_browsers_cache", _p=["confirm"]: getattr(
        _get(_k), _m
    )(**_pick(d, _p)),
    # -- OfficeControl --
    "appctl_office_get_install_info": lambda d, _k="office", _m="get_office_install_info", _p=[]: getattr(_get(_k), _m)(
        **_pick(d, _p)
    ),
    "appctl_office_list_installed_apps": lambda d, _k="office", _m="list_installed_office_apps", _p=[]: getattr(
        _get(_k), _m
    )(**_pick(d, _p)),
    "appctl_office_set_update_channel": lambda d, _k="office", _m="set_update_channel", _p=[
        "channel",
        "confirm",
    ]: getattr(_get(_k), _m)(**_pick(d, _p)),
    "appctl_office_close_all": lambda d, _k="office", _m="close_all_office_apps", _p=["confirm"]: getattr(_get(_k), _m)(
        **_pick(d, _p)
    ),
    # -- MediaControl --
    "appctl_media_play_pause": lambda d, _k="media", _m="play_pause", _p=[]: getattr(_get(_k), _m)(**_pick(d, _p)),
    "appctl_media_stop": lambda d, _k="media", _m="stop", _p=[]: getattr(_get(_k), _m)(**_pick(d, _p)),
    "appctl_media_next_track": lambda d, _k="media", _m="next_track", _p=[]: getattr(_get(_k), _m)(**_pick(d, _p)),
    "appctl_media_previous_track": lambda d, _k="media", _m="previous_track", _p=[]: getattr(_get(_k), _m)(
        **_pick(d, _p)
    ),
    "appctl_media_set_mute": lambda d, _k="media", _m="set_mute", _p=["muted"]: getattr(_get(_k), _m)(**_pick(d, _p)),
    "appctl_media_volume_up": lambda d, _k="media", _m="volume_up", _p=["steps"]: getattr(_get(_k), _m)(**_pick(d, _p)),
    "appctl_media_volume_down": lambda d, _k="media", _m="volume_down", _p=["steps"]: getattr(_get(_k), _m)(
        **_pick(d, _p)
    ),
    "appctl_media_get_now_playing": lambda d, _k="media", _m="get_now_playing_info", _p=[]: getattr(_get(_k), _m)(
        **_pick(d, _p)
    ),
    # -- CommunicationControl --
    "appctl_comm_list_installed": lambda d, _k="comm", _m="list_installed_comm_apps", _p=[]: getattr(_get(_k), _m)(
        **_pick(d, _p)
    ),
    "appctl_comm_get_startup_status": lambda d, _k="comm", _m="get_startup_status", _p=[]: getattr(_get(_k), _m)(
        **_pick(d, _p)
    ),
    "appctl_comm_close_all": lambda d, _k="comm", _m="close_all_comm_apps", _p=["confirm"]: getattr(_get(_k), _m)(
        **_pick(d, _p)
    ),
}
