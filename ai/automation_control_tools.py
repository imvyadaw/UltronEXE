"""System automation tool registry
===================================
Wires system_control/automation/* (PowerShellScriptManager,
BatchScriptManager, WindowsEventTrigger, SystemAutomationPipeline,
SystemMacroEngine, BackupScheduler, MaintenanceScheduler,
UpdateScheduler, CleanupScheduler, SmartNotificationRouter) into the
AI tool-calling loop.
Same pattern as ai/ui_control_tools.py and ai/security_control_tools.py:
lazy singletons + a flat AUTOMATION_CONTROL_TOOLS /
AUTOMATION_CONTROL_DIRECT_HANDLERS pair, merged at the bottom of
ai/tools_schema.py and ai/tool_runtime.py respectively.

Naming: every tool is prefixed `sysauto_` to avoid colliding with the
existing generic `automation_*`/workflow/macro-flavoured tools that
front the app-agnostic automation/ package (see each module's own
docstring in system_control/automation/ for the full distinction).

Confirm-gating mirrors whatever the underlying manager methods already
decided (save/list/view calls are ungated, run/delete/create calls are
gated) rather than gating everything uniformly here.
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

    if key == "powershell":
        from system_control.automation.powershell_manager import PowerShellScriptManager

        obj = PowerShellScriptManager()
    elif key == "batch":
        from system_control.automation.batch_manager import BatchScriptManager

        obj = BatchScriptManager()
    elif key == "event_trigger":
        from system_control.automation.event_triggers import WindowsEventTrigger

        obj = WindowsEventTrigger()
    elif key == "pipeline":
        from system_control.automation.workflow_engine import SystemAutomationPipeline

        obj = SystemAutomationPipeline()
    elif key == "macro":
        from system_control.automation.macro_engine import SystemMacroEngine

        obj = SystemMacroEngine()
    elif key == "backup_sched":
        from system_control.automation.backup_scheduler import BackupScheduler

        obj = BackupScheduler()
    elif key == "maintenance_sched":
        from system_control.automation.maintenance_scheduler import MaintenanceScheduler

        obj = MaintenanceScheduler()
    elif key == "update_sched":
        from system_control.automation.update_scheduler import UpdateScheduler

        obj = UpdateScheduler()
    elif key == "cleanup_sched":
        from system_control.automation.cleanup_scheduler import CleanupScheduler

        obj = CleanupScheduler()
    elif key == "smart_notif":
        from system_control.automation.smart_notifications import SmartNotificationRouter

        obj = SmartNotificationRouter()
    else:
        raise KeyError(key)

    _instances[key] = obj
    return obj


# ---------------------------------------------------------------------------
# Tool schemas
# ---------------------------------------------------------------------------
AUTOMATION_CONTROL_TOOLS = [
    # -- PowerShellScriptManager --
    _tool(
        "sysauto_ps_save_script",
        "Save a named PowerShell script for later reuse.",
        {"name": {"type": "string"}, "content": {"type": "string"}},
        ["name", "content"],
    ),
    _tool("sysauto_ps_list_scripts", "List all saved PowerShell scripts."),
    _tool("sysauto_ps_get_script", "View a saved PowerShell script's content.", {"name": {"type": "string"}}, ["name"]),
    _tool(
        "sysauto_ps_delete_script",
        "Delete a saved PowerShell script.",
        {"name": {"type": "string"}, "confirm": {"type": "boolean"}},
        ["name"],
    ),
    _tool(
        "sysauto_ps_run_script",
        "Run a saved PowerShell script by name.",
        {"name": {"type": "string"}, "timeout": {"type": "integer"}, "confirm": {"type": "boolean"}},
        ["name"],
    ),
    _tool(
        "sysauto_ps_run_adhoc",
        "Run a one-off PowerShell command/script string without saving it.",
        {"script": {"type": "string"}, "timeout": {"type": "integer"}},
        ["script"],
    ),
    _tool(
        "sysauto_ps_get_execution_policy",
        "Read the current PowerShell execution policy for a scope.",
        {"scope": {"type": "string"}},
    ),
    _tool(
        "sysauto_ps_set_execution_policy",
        "Set the PowerShell execution policy for a scope.",
        {"policy": {"type": "string"}, "scope": {"type": "string"}, "confirm": {"type": "boolean"}},
        ["policy"],
    ),
    # -- BatchScriptManager --
    _tool(
        "sysauto_bat_save_script",
        "Save a named batch (.bat) script for later reuse.",
        {"name": {"type": "string"}, "content": {"type": "string"}},
        ["name", "content"],
    ),
    _tool("sysauto_bat_list_scripts", "List all saved batch scripts."),
    _tool("sysauto_bat_get_script", "View a saved batch script's content.", {"name": {"type": "string"}}, ["name"]),
    _tool(
        "sysauto_bat_delete_script",
        "Delete a saved batch script.",
        {"name": {"type": "string"}, "confirm": {"type": "boolean"}},
        ["name"],
    ),
    _tool(
        "sysauto_bat_run_script",
        "Run a saved batch script by name.",
        {
            "name": {"type": "string"},
            "arguments": {"type": "string"},
            "timeout": {"type": "integer"},
            "confirm": {"type": "boolean"},
        },
        ["name"],
    ),
    _tool(
        "sysauto_bat_run_adhoc",
        "Run a one-off shell/cmd command without saving it.",
        {"command": {"type": "string"}, "timeout": {"type": "integer"}},
        ["command"],
    ),
    # -- WindowsEventTrigger --
    _tool("sysauto_trigger_list", "List all registered native Windows event triggers."),
    _tool(
        "sysauto_trigger_remove",
        "Stop and remove a registered native event trigger.",
        {"trigger_id": {"type": "string"}},
        ["trigger_id"],
    ),
    _tool("sysauto_trigger_stop_all", "Stop native-event polling and clear all triggers."),
    # -- SystemAutomationPipeline --
    _tool(
        "sysauto_pipeline_save",
        "Save a named pipeline of native jobs (powershell/batch/backup/wait steps).",
        {"name": {"type": "string"}, "steps": {"type": "array", "items": {"type": "object"}}},
        ["name", "steps"],
    ),
    _tool("sysauto_pipeline_list", "List all saved system automation pipelines."),
    _tool("sysauto_pipeline_get", "View a saved pipeline's steps.", {"name": {"type": "string"}}, ["name"]),
    _tool(
        "sysauto_pipeline_delete",
        "Delete a saved pipeline.",
        {"name": {"type": "string"}, "confirm": {"type": "boolean"}},
        ["name"],
    ),
    _tool(
        "sysauto_pipeline_run",
        "Run a saved pipeline of native jobs step by step.",
        {"name": {"type": "string"}, "stop_on_error": {"type": "boolean"}, "confirm": {"type": "boolean"}},
        ["name"],
    ),
    # -- SystemMacroEngine --
    _tool(
        "sysauto_macro_save",
        "Save a named macro chaining multiple system_control manager method calls.",
        {"name": {"type": "string"}, "steps": {"type": "array", "items": {"type": "object"}}},
        ["name", "steps"],
    ),
    _tool("sysauto_macro_list", "List all saved system macros."),
    _tool("sysauto_macro_get", "View a saved macro's steps.", {"name": {"type": "string"}}, ["name"]),
    _tool(
        "sysauto_macro_delete",
        "Delete a saved macro.",
        {"name": {"type": "string"}, "confirm": {"type": "boolean"}},
        ["name"],
    ),
    _tool(
        "sysauto_macro_run",
        "Run a saved macro (a chain of system_control changes) in one shot.",
        {"name": {"type": "string"}, "stop_on_error": {"type": "boolean"}, "confirm": {"type": "boolean"}},
        ["name"],
    ),
    # -- BackupScheduler --
    _tool(
        "sysauto_backup_create_job",
        "Create a recurring backup job for one or more paths on a schedule.",
        {
            "job_name": {"type": "string"},
            "paths": {"type": "array", "items": {"type": "string"}},
            "trigger_type": {"type": "string", "enum": ["daily", "logon"]},
            "time": {"type": "string"},
            "retention_count": {"type": "integer"},
            "confirm": {"type": "boolean"},
        },
        ["job_name", "paths"],
    ),
    _tool("sysauto_backup_list_jobs", "List all recurring backup jobs."),
    _tool(
        "sysauto_backup_get_job", "View one backup job's configuration.", {"job_name": {"type": "string"}}, ["job_name"]
    ),
    _tool(
        "sysauto_backup_delete_job",
        "Delete a backup job and its underlying scheduled task.",
        {"job_name": {"type": "string"}, "confirm": {"type": "boolean"}},
        ["job_name"],
    ),
    _tool(
        "sysauto_backup_set_enabled",
        "Enable or disable a backup job without deleting it.",
        {"job_name": {"type": "string"}, "enabled": {"type": "boolean"}, "confirm": {"type": "boolean"}},
        ["job_name", "enabled"],
    ),
    _tool(
        "sysauto_backup_run_now",
        "Run a backup job's backups immediately, outside its schedule.",
        {"job_name": {"type": "string"}, "confirm": {"type": "boolean"}},
        ["job_name"],
    ),
    # -- MaintenanceScheduler --
    _tool(
        "sysauto_maint_create_job",
        "Create a recurring OS maintenance job (SFC scan, DISM health check, Optimize-Volume).",
        {
            "job_name": {"type": "string"},
            "tasks": {
                "type": "array",
                "items": {"type": "string", "enum": ["sfc_scan", "dism_health", "optimize_volume"]},
            },
            "trigger_type": {"type": "string", "enum": ["daily", "logon"]},
            "time": {"type": "string"},
            "drive_letter": {"type": "string"},
            "confirm": {"type": "boolean"},
        },
        ["job_name", "tasks"],
    ),
    _tool("sysauto_maint_list_jobs", "List all recurring maintenance jobs."),
    _tool(
        "sysauto_maint_get_job",
        "View one maintenance job's configuration.",
        {"job_name": {"type": "string"}},
        ["job_name"],
    ),
    _tool(
        "sysauto_maint_delete_job",
        "Delete a maintenance job and its underlying scheduled task.",
        {"job_name": {"type": "string"}, "confirm": {"type": "boolean"}},
        ["job_name"],
    ),
    _tool(
        "sysauto_maint_set_enabled",
        "Enable or disable a maintenance job without deleting it.",
        {"job_name": {"type": "string"}, "enabled": {"type": "boolean"}, "confirm": {"type": "boolean"}},
        ["job_name", "enabled"],
    ),
    _tool(
        "sysauto_maint_run_now",
        "Run a maintenance job's tasks immediately, outside its schedule.",
        {"job_name": {"type": "string"}, "confirm": {"type": "boolean"}},
        ["job_name"],
    ),
    # -- UpdateScheduler --
    _tool(
        "sysauto_update_create_job",
        "Create a recurring Windows Update check (and optionally silent install) job.",
        {
            "job_name": {"type": "string"},
            "trigger_type": {"type": "string", "enum": ["daily", "logon"]},
            "time": {"type": "string"},
            "auto_install": {"type": "boolean"},
            "confirm": {"type": "boolean"},
        },
        ["job_name"],
    ),
    _tool("sysauto_update_list_jobs", "List all recurring Windows Update jobs."),
    _tool(
        "sysauto_update_get_job",
        "View one Windows Update job's configuration.",
        {"job_name": {"type": "string"}},
        ["job_name"],
    ),
    _tool(
        "sysauto_update_delete_job",
        "Delete a Windows Update job and its underlying scheduled task.",
        {"job_name": {"type": "string"}, "confirm": {"type": "boolean"}},
        ["job_name"],
    ),
    _tool(
        "sysauto_update_set_enabled",
        "Enable or disable a Windows Update job without deleting it.",
        {"job_name": {"type": "string"}, "enabled": {"type": "boolean"}, "confirm": {"type": "boolean"}},
        ["job_name", "enabled"],
    ),
    _tool(
        "sysauto_update_run_now",
        "Run a Windows Update job immediately, outside its schedule.",
        {"job_name": {"type": "string"}, "confirm": {"type": "boolean"}},
        ["job_name"],
    ),
    # -- CleanupScheduler --
    _tool(
        "sysauto_cleanup_create_job",
        "Create a recurring disk cleanup job (temp files, Recycle Bin, Storage Sense).",
        {
            "job_name": {"type": "string"},
            "targets": {
                "type": "array",
                "items": {"type": "string", "enum": ["temp_files", "recycle_bin", "storage_sense"]},
            },
            "trigger_type": {"type": "string", "enum": ["daily", "logon"]},
            "time": {"type": "string"},
            "confirm": {"type": "boolean"},
        },
        ["job_name", "targets"],
    ),
    _tool("sysauto_cleanup_list_jobs", "List all recurring cleanup jobs."),
    _tool(
        "sysauto_cleanup_get_job",
        "View one cleanup job's configuration.",
        {"job_name": {"type": "string"}},
        ["job_name"],
    ),
    _tool(
        "sysauto_cleanup_delete_job",
        "Delete a cleanup job and its underlying scheduled task.",
        {"job_name": {"type": "string"}, "confirm": {"type": "boolean"}},
        ["job_name"],
    ),
    _tool(
        "sysauto_cleanup_set_enabled",
        "Enable or disable a cleanup job without deleting it.",
        {"job_name": {"type": "string"}, "enabled": {"type": "boolean"}, "confirm": {"type": "boolean"}},
        ["job_name", "enabled"],
    ),
    _tool(
        "sysauto_cleanup_run_now",
        "Run a cleanup job's targets immediately, outside its schedule.",
        {"job_name": {"type": "string"}, "confirm": {"type": "boolean"}},
        ["job_name"],
    ),
    # -- SmartNotificationRouter --
    _tool(
        "sysauto_notif_save_rule",
        "Save a named quiet-hours/priority rule for routing notifications.",
        {
            "rule_name": {"type": "string"},
            "quiet_hours_start": {"type": "string"},
            "quiet_hours_end": {"type": "string"},
            "min_priority_during_quiet_hours": {"type": "string", "enum": ["low", "normal", "high", "urgent"]},
            "suppress_during_focus_assist": {"type": "boolean"},
        },
        ["rule_name"],
    ),
    _tool("sysauto_notif_list_rules", "List all saved notification routing rules."),
    _tool(
        "sysauto_notif_get_rule",
        "View one saved notification routing rule.",
        {"rule_name": {"type": "string"}},
        ["rule_name"],
    ),
    _tool(
        "sysauto_notif_delete_rule",
        "Delete a saved notification routing rule.",
        {"rule_name": {"type": "string"}},
        ["rule_name"],
    ),
    _tool(
        "sysauto_notif_route",
        "Route a notification through a named rule: show now, or queue it if quiet hours/Focus Assist say to wait.",
        {
            "title": {"type": "string"},
            "message": {"type": "string"},
            "priority": {"type": "string", "enum": ["low", "normal", "high", "urgent"]},
            "rule_name": {"type": "string"},
            "duration": {"type": "integer"},
        },
        ["title", "message"],
    ),
    _tool("sysauto_notif_get_queued", "List notifications currently held back, waiting for a flush."),
    _tool("sysauto_notif_clear_queue", "Discard everything currently queued without showing it."),
    _tool(
        "sysauto_notif_flush_queued",
        "Show every currently-queued notification now, highest priority first.",
        {"duration": {"type": "integer"}},
    ),
]


# ---------------------------------------------------------------------------
# Direct handlers (tool name -> callable(args_dict) -> result dict)
# ---------------------------------------------------------------------------
AUTOMATION_CONTROL_DIRECT_HANDLERS = {
    # -- PowerShellScriptManager --
    "sysauto_ps_save_script": lambda d, _k="powershell", _m="save_script", _p=["name", "content"]: getattr(
        _get(_k), _m
    )(**_pick(d, _p)),
    "sysauto_ps_list_scripts": lambda d, _k="powershell", _m="list_scripts", _p=[]: getattr(_get(_k), _m)(
        **_pick(d, _p)
    ),
    "sysauto_ps_get_script": lambda d, _k="powershell", _m="get_script", _p=["name"]: getattr(_get(_k), _m)(
        **_pick(d, _p)
    ),
    "sysauto_ps_delete_script": lambda d, _k="powershell", _m="delete_script", _p=["name", "confirm"]: getattr(
        _get(_k), _m
    )(**_pick(d, _p)),
    "sysauto_ps_run_script": lambda d, _k="powershell", _m="run_script", _p=["name", "timeout", "confirm"]: getattr(
        _get(_k), _m
    )(**_pick(d, _p)),
    "sysauto_ps_run_adhoc": lambda d, _k="powershell", _m="run_adhoc", _p=["script", "timeout"]: getattr(_get(_k), _m)(
        **_pick(d, _p)
    ),
    "sysauto_ps_get_execution_policy": lambda d, _k="powershell", _m="get_execution_policy", _p=["scope"]: getattr(
        _get(_k), _m
    )(**_pick(d, _p)),
    "sysauto_ps_set_execution_policy": lambda d, _k="powershell", _m="set_execution_policy", _p=[
        "policy",
        "scope",
        "confirm",
    ]: getattr(_get(_k), _m)(**_pick(d, _p)),
    # -- BatchScriptManager --
    "sysauto_bat_save_script": lambda d, _k="batch", _m="save_script", _p=["name", "content"]: getattr(_get(_k), _m)(
        **_pick(d, _p)
    ),
    "sysauto_bat_list_scripts": lambda d, _k="batch", _m="list_scripts", _p=[]: getattr(_get(_k), _m)(**_pick(d, _p)),
    "sysauto_bat_get_script": lambda d, _k="batch", _m="get_script", _p=["name"]: getattr(_get(_k), _m)(**_pick(d, _p)),
    "sysauto_bat_delete_script": lambda d, _k="batch", _m="delete_script", _p=["name", "confirm"]: getattr(
        _get(_k), _m
    )(**_pick(d, _p)),
    "sysauto_bat_run_script": lambda d, _k="batch", _m="run_script", _p=[
        "name",
        "arguments",
        "timeout",
        "confirm",
    ]: getattr(_get(_k), _m)(**_pick(d, _p)),
    "sysauto_bat_run_adhoc": lambda d, _k="batch", _m="run_adhoc", _p=["command", "timeout"]: getattr(_get(_k), _m)(
        **_pick(d, _p)
    ),
    # -- WindowsEventTrigger --
    "sysauto_trigger_list": lambda d, _k="event_trigger", _m="list_triggers", _p=[]: getattr(_get(_k), _m)(
        **_pick(d, _p)
    ),
    "sysauto_trigger_remove": lambda d, _k="event_trigger", _m="remove_trigger", _p=["trigger_id"]: getattr(
        _get(_k), _m
    )(**_pick(d, _p)),
    "sysauto_trigger_stop_all": lambda d, _k="event_trigger", _m="stop_all", _p=[]: getattr(_get(_k), _m)(
        **_pick(d, _p)
    ),
    # -- SystemAutomationPipeline --
    "sysauto_pipeline_save": lambda d, _k="pipeline", _m="save_pipeline", _p=["name", "steps"]: getattr(_get(_k), _m)(
        **_pick(d, _p)
    ),
    "sysauto_pipeline_list": lambda d, _k="pipeline", _m="list_pipelines", _p=[]: getattr(_get(_k), _m)(**_pick(d, _p)),
    "sysauto_pipeline_get": lambda d, _k="pipeline", _m="get_pipeline", _p=["name"]: getattr(_get(_k), _m)(
        **_pick(d, _p)
    ),
    "sysauto_pipeline_delete": lambda d, _k="pipeline", _m="delete_pipeline", _p=["name", "confirm"]: getattr(
        _get(_k), _m
    )(**_pick(d, _p)),
    "sysauto_pipeline_run": lambda d, _k="pipeline", _m="run_pipeline", _p=[
        "name",
        "stop_on_error",
        "confirm",
    ]: getattr(_get(_k), _m)(**_pick(d, _p)),
    # -- SystemMacroEngine --
    "sysauto_macro_save": lambda d, _k="macro", _m="save_macro", _p=["name", "steps"]: getattr(_get(_k), _m)(
        **_pick(d, _p)
    ),
    "sysauto_macro_list": lambda d, _k="macro", _m="list_macros", _p=[]: getattr(_get(_k), _m)(**_pick(d, _p)),
    "sysauto_macro_get": lambda d, _k="macro", _m="get_macro", _p=["name"]: getattr(_get(_k), _m)(**_pick(d, _p)),
    "sysauto_macro_delete": lambda d, _k="macro", _m="delete_macro", _p=["name", "confirm"]: getattr(_get(_k), _m)(
        **_pick(d, _p)
    ),
    "sysauto_macro_run": lambda d, _k="macro", _m="run_macro", _p=["name", "stop_on_error", "confirm"]: getattr(
        _get(_k), _m
    )(**_pick(d, _p)),
    # -- BackupScheduler --
    "sysauto_backup_create_job": lambda d, _k="backup_sched", _m="create_job", _p=[
        "job_name",
        "paths",
        "trigger_type",
        "time",
        "retention_count",
        "confirm",
    ]: getattr(_get(_k), _m)(**_pick(d, _p)),
    "sysauto_backup_list_jobs": lambda d, _k="backup_sched", _m="list_jobs", _p=[]: getattr(_get(_k), _m)(
        **_pick(d, _p)
    ),
    "sysauto_backup_get_job": lambda d, _k="backup_sched", _m="get_job", _p=["job_name"]: getattr(_get(_k), _m)(
        **_pick(d, _p)
    ),
    "sysauto_backup_delete_job": lambda d, _k="backup_sched", _m="delete_job", _p=["job_name", "confirm"]: getattr(
        _get(_k), _m
    )(**_pick(d, _p)),
    "sysauto_backup_set_enabled": lambda d, _k="backup_sched", _m="set_job_enabled", _p=[
        "job_name",
        "enabled",
        "confirm",
    ]: getattr(_get(_k), _m)(**_pick(d, _p)),
    "sysauto_backup_run_now": lambda d, _k="backup_sched", _m="run_job_now", _p=["job_name", "confirm"]: getattr(
        _get(_k), _m
    )(**_pick(d, _p)),
    # -- MaintenanceScheduler --
    "sysauto_maint_create_job": lambda d, _k="maintenance_sched", _m="create_job", _p=[
        "job_name",
        "tasks",
        "trigger_type",
        "time",
        "drive_letter",
        "confirm",
    ]: getattr(_get(_k), _m)(**_pick(d, _p)),
    "sysauto_maint_list_jobs": lambda d, _k="maintenance_sched", _m="list_jobs", _p=[]: getattr(_get(_k), _m)(
        **_pick(d, _p)
    ),
    "sysauto_maint_get_job": lambda d, _k="maintenance_sched", _m="get_job", _p=["job_name"]: getattr(_get(_k), _m)(
        **_pick(d, _p)
    ),
    "sysauto_maint_delete_job": lambda d, _k="maintenance_sched", _m="delete_job", _p=["job_name", "confirm"]: getattr(
        _get(_k), _m
    )(**_pick(d, _p)),
    "sysauto_maint_set_enabled": lambda d, _k="maintenance_sched", _m="set_job_enabled", _p=[
        "job_name",
        "enabled",
        "confirm",
    ]: getattr(_get(_k), _m)(**_pick(d, _p)),
    "sysauto_maint_run_now": lambda d, _k="maintenance_sched", _m="run_job_now", _p=["job_name", "confirm"]: getattr(
        _get(_k), _m
    )(**_pick(d, _p)),
    # -- UpdateScheduler --
    "sysauto_update_create_job": lambda d, _k="update_sched", _m="create_job", _p=[
        "job_name",
        "trigger_type",
        "time",
        "auto_install",
        "confirm",
    ]: getattr(_get(_k), _m)(**_pick(d, _p)),
    "sysauto_update_list_jobs": lambda d, _k="update_sched", _m="list_jobs", _p=[]: getattr(_get(_k), _m)(
        **_pick(d, _p)
    ),
    "sysauto_update_get_job": lambda d, _k="update_sched", _m="get_job", _p=["job_name"]: getattr(_get(_k), _m)(
        **_pick(d, _p)
    ),
    "sysauto_update_delete_job": lambda d, _k="update_sched", _m="delete_job", _p=["job_name", "confirm"]: getattr(
        _get(_k), _m
    )(**_pick(d, _p)),
    "sysauto_update_set_enabled": lambda d, _k="update_sched", _m="set_job_enabled", _p=[
        "job_name",
        "enabled",
        "confirm",
    ]: getattr(_get(_k), _m)(**_pick(d, _p)),
    "sysauto_update_run_now": lambda d, _k="update_sched", _m="run_job_now", _p=["job_name", "confirm"]: getattr(
        _get(_k), _m
    )(**_pick(d, _p)),
    # -- CleanupScheduler --
    "sysauto_cleanup_create_job": lambda d, _k="cleanup_sched", _m="create_job", _p=[
        "job_name",
        "targets",
        "trigger_type",
        "time",
        "confirm",
    ]: getattr(_get(_k), _m)(**_pick(d, _p)),
    "sysauto_cleanup_list_jobs": lambda d, _k="cleanup_sched", _m="list_jobs", _p=[]: getattr(_get(_k), _m)(
        **_pick(d, _p)
    ),
    "sysauto_cleanup_get_job": lambda d, _k="cleanup_sched", _m="get_job", _p=["job_name"]: getattr(_get(_k), _m)(
        **_pick(d, _p)
    ),
    "sysauto_cleanup_delete_job": lambda d, _k="cleanup_sched", _m="delete_job", _p=["job_name", "confirm"]: getattr(
        _get(_k), _m
    )(**_pick(d, _p)),
    "sysauto_cleanup_set_enabled": lambda d, _k="cleanup_sched", _m="set_job_enabled", _p=[
        "job_name",
        "enabled",
        "confirm",
    ]: getattr(_get(_k), _m)(**_pick(d, _p)),
    "sysauto_cleanup_run_now": lambda d, _k="cleanup_sched", _m="run_job_now", _p=["job_name", "confirm"]: getattr(
        _get(_k), _m
    )(**_pick(d, _p)),
    # -- SmartNotificationRouter --
    "sysauto_notif_save_rule": lambda d, _k="smart_notif", _m="save_rule", _p=[
        "rule_name",
        "quiet_hours_start",
        "quiet_hours_end",
        "min_priority_during_quiet_hours",
        "suppress_during_focus_assist",
    ]: getattr(_get(_k), _m)(**_pick(d, _p)),
    "sysauto_notif_list_rules": lambda d, _k="smart_notif", _m="list_rules", _p=[]: getattr(_get(_k), _m)(
        **_pick(d, _p)
    ),
    "sysauto_notif_get_rule": lambda d, _k="smart_notif", _m="get_rule", _p=["rule_name"]: getattr(_get(_k), _m)(
        **_pick(d, _p)
    ),
    "sysauto_notif_delete_rule": lambda d, _k="smart_notif", _m="delete_rule", _p=["rule_name"]: getattr(_get(_k), _m)(
        **_pick(d, _p)
    ),
    "sysauto_notif_route": lambda d, _k="smart_notif", _m="route", _p=[
        "title",
        "message",
        "priority",
        "rule_name",
        "duration",
    ]: getattr(_get(_k), _m)(**_pick(d, _p)),
    "sysauto_notif_get_queued": lambda d, _k="smart_notif", _m="get_queued", _p=[]: getattr(_get(_k), _m)(
        **_pick(d, _p)
    ),
    "sysauto_notif_clear_queue": lambda d, _k="smart_notif", _m="clear_queue", _p=[]: getattr(_get(_k), _m)(
        **_pick(d, _p)
    ),
    "sysauto_notif_flush_queued": lambda d, _k="smart_notif", _m="flush_queued", _p=["duration"]: getattr(_get(_k), _m)(
        **_pick(d, _p)
    ),
}
