"""
Permissions
===========
Confirmation gate for destructive actions. Enforcement itself lives at
each tool's own `confirm: bool = False` parameter (see
windows/system_info/power.py, windows/process/process.py, etc.) - this
class is the single source of truth for *which* tools are considered
destructive, so callers (executor, plugins, future agents) can check
`requires_confirmation()` before calling instead of needing to know
that convention lives in each individual module.
"""


class PermissionGate:
    DESTRUCTIVE_TOOLS = {
        "shutdown_pc",
        "restart_pc",
        "sign_out",
        "delete_file",
        "delete_folder",
        "kill_process",
        # NOTE: stop_service, remove_rule, remove_startup_program, delete_value,
        # and clear_downloads were dead legacy names here - no registered tool
        # has ever been called that. They silently gave zero real coverage.
        # The actual current tools that do this destructive work were never
        # added under their real names, so ActionPipeline's central gate never
        # asked for confirmation on them (each still has its own local
        # confirm=True check, but the central single-source-of-truth gate
        # missed them entirely). Replaced with the real registered names below.
        # "delete_value" -> already covered by "sysconfig_registry_delete_value" below
        # "remove_startup_program" -> already covered by "procctl_startup_remove" below
        "netctl_ssh_stop_service",  # was "stop_service"
        "netctl_firewall_remove_rule",
        "specctl_context_remove_rule",  # was "remove_rule"
        "edge_dl_clear_downloads",
        "chrome_dl_clear_downloads",
        "firefox_dl_clear_downloads",  # was "clear_downloads"
        # Raw command execution - arbitrary shell/PowerShell access is at
        # least as destructive as any single action above (it can do all
        # of them and more), but was missing from this set, so
        # ActionPipeline never asked for confirmation before running one.
        "run_command",
        "run_powershell",
        # call_phone (PHASE_18_7_AUTOMATION/ACTIONS/call_phone.py) places
        # a real phone call - was missing from this set even though its
        # own executor.py handler already enforces its own confirm=true
        # check inline; adding it here too means ActionPipeline's central
        # gate catches it the same consistent way as every other
        # real-world action above, instead of relying solely on that one
        # tool's local check.
        "call_phone",
        # relaunch_as_admin (windows/system_info/admin.py) closes the
        # current Ultron session and reopens it elevated - same
        # end-the-current-process risk class as shutdown_pc/restart_pc,
        # so it belongs in the same central gate as those.
        "relaunch_as_admin",
        # system_control/system_config/* (ai/system_config_tools.py) -
        # registry writes/deletes, env var writes/deletes, device
        # enable/disable, and Windows Update installs all change durable
        # system state (or, for device disable, can cut off input/network
        # hardware ULTRON itself needs) - same central gate as every other
        # real-world action above, on top of each tool's own inline
        # confirm=True check.
        "sysconfig_registry_set_value",
        "sysconfig_registry_create_key",
        "sysconfig_registry_delete_value",
        "sysconfig_registry_delete_key",
        "sysconfig_registry_restore_json",
        "sysconfig_registry_import_reg_file",
        "sysconfig_env_set",
        "sysconfig_env_delete",
        "sysconfig_set_computer_description",
        "sysconfig_device_enable",
        "sysconfig_device_disable",
        "sysconfig_update_install",
        "sysconfig_update_pause",
        # sysconfig_restore_* / sysconfig_bios_* (ai/system_config_tools.py,
        # backed by system_control/system_config/system_restore.py and
        # bios_uefi.py) - restore_to_point reverts installed programs and
        # forces an immediate reboot, and restart_to_firmware_settings
        # interrupts the session immediately, same risk class as
        # shutdown_pc/restart_pc above.
        "sysconfig_restore_to_point",
        "sysconfig_restore_enable_protection",
        "sysconfig_restore_disable_protection",
        "sysconfig_bios_restart_to_firmware_settings",
        # procctl_* (ai/process_control_tools.py, backed by
        # system_control/process/*) - startup entries and scheduled tasks
        # are persistent state that runs unattended later, and killing a
        # process ends it immediately - same central gate as every other
        # real-world action above, on top of each tool's own inline
        # confirm=True check and background_apps.py's separate
        # protected-process refusal.
        "procctl_startup_add",
        "procctl_startup_remove",
        "procctl_startup_enable",
        "procctl_startup_disable",
        "procctl_process_kill",
        "procctl_task_create",
        "procctl_task_delete",
        "procctl_task_enable",
        "procctl_task_disable",
        "procctl_task_run_now",
        # filectl_* (ai/file_control_tools.py, backed by
        # system_control/files/*) - encrypting/decrypting overwrites file
        # contents, ACL/ownership changes can affect who can access a
        # file (including locking ULTRON or the user out), sharing a
        # folder exposes it on the network, mirror-sync deletes files in
        # the destination, and backup deletion/restore both overwrite
        # state - same central gate as every other real-world action
        # above.
        "filectl_encrypt_file",
        "filectl_decrypt_file",
        "filectl_set_permission",
        "filectl_remove_permission",
        "filectl_take_ownership",
        "filectl_share_folder",
        "filectl_unshare_folder",
        "filectl_sync_folders",
        "filectl_delete_backup",
        "filectl_restore_from_backup",
        "filectl_restore_from_recycle_bin",
        # appctl_* (ai/application_control_tools.py, backed by
        # system_control/applications/*) - installing/uninstalling
        # software, forcing run-as-admin or resetting a Store app,
        # overwriting AppData via restore, and deleting cache/leftover
        # files are all durable, hard-to-reverse system changes - same
        # central gate as every other real-world action above, on top of
        # each tool's own inline confirm=True check.
        "appctl_pkg_install",
        "appctl_uninstall_app",
        "appctl_uninstall_appx",
        "appctl_uninstall_force_remove_leftovers",
        "appctl_update_app",
        "appctl_update_all",
        "appctl_settings_set_run_as_admin",
        "appctl_settings_set_execution_alias",
        "appctl_settings_reset_app",
        "appctl_data_backup",
        "appctl_data_restore",
        "appctl_cache_clear",
        "appctl_cache_clear_store",
        # appctl_defaults_import (default_apps.py) - changes many file-
        # type/protocol defaults machine-wide in one shot via DISM.
        "appctl_defaults_import",
        # appctl_exec_* (app_permissions.py) - locks a program out of
        # launching (or removes that lock) for this user; toggling
        # enforcement off silently defeats every existing block at once.
        "appctl_exec_set_restricted",
        "appctl_exec_block",
        "appctl_exec_allow",
        # appctl_browser_close_all / clear_all_cache (browser_control.py)
        # - force-closes every running browser with no save prompt, and
        # deletes disk cache outright.
        "appctl_browser_close_all",
        "appctl_browser_clear_all_cache",
        # appctl_office_set_update_channel / close_all (office_control.py)
        # - changes which Office builds this machine receives, and
        # force-closes Office apps with unsaved documents open.
        "appctl_office_set_update_channel",
        "appctl_office_close_all",
        # appctl_comm_close_all (communication_control.py) - force-closes
        # every running communication app, dropping any active calls.
        "appctl_comm_close_all",
    }

    def requires_confirmation(self, tool_name: str) -> bool:
        return tool_name in self.DESTRUCTIVE_TOOLS
