"""Process Control tool registry
=================================
Wires system_control/process/* (startup manager, background/running
apps, native Windows Task Scheduler) into the AI tool-calling loop.
Same pattern as ai/system_config_tools.py: lazy singletons + a flat
PROCESS_CONTROL_TOOLS / PROCESS_CONTROL_DIRECT_HANDLERS pair, merged
at the bottom of ai/tools_schema.py and ai/tool_runtime.py
respectively (see the two-line imports there).

Naming: every tool is prefixed `procctl_` to avoid colliding with
ai/system_config_tools.py's `sysconfig_*` tools and any existing
process-related tools elsewhere in the codebase (e.g. plain
task-scheduling tools backed by automation/scheduler/task_scheduler.py's
in-process TaskScheduler, which is a different thing from the native
Windows Task Scheduler wrapped here).

Every write/enable/disable/kill/create/delete/run method on the
underlying classes is confirm-gated (confirm: bool, defaults False) -
same pattern as every other destructive tool in this codebase.
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

    if key == "startup_manager":
        from system_control.process.startup_manager import StartupManager

        obj = StartupManager()
    elif key == "background_apps":
        from system_control.process.background_apps import BackgroundApps

        obj = BackgroundApps()
    elif key == "task_scheduler":
        from system_control.process.task_scheduler import WindowsTaskScheduler

        obj = WindowsTaskScheduler()
    else:
        raise KeyError(f"Unknown process_control tool key: {key}")

    _instances[key] = obj
    return obj


# ---------------------------------------------------------------------------
# Tool schemas
# ---------------------------------------------------------------------------
PROCESS_CONTROL_TOOLS = [
    # -- StartupManager --
    _tool(
        "procctl_startup_list",
        "List every startup entry (Run/RunOnce registry keys plus the Startup folder, for the "
        "current user and all users).",
    ),
    _tool(
        "procctl_startup_add",
        "Add a program to the current user's startup (HKCU Run key). Confirm-gated.",
        {"name": {"type": "string"}, "command": {"type": "string"}, "confirm": {"type": "boolean"}},
        ["name", "command"],
    ),
    _tool(
        "procctl_startup_remove",
        "Remove a program from the current user's startup (HKCU Run key). Confirm-gated.",
        {"name": {"type": "string"}, "confirm": {"type": "boolean"}},
        ["name"],
    ),
    _tool(
        "procctl_startup_enable",
        "Re-enable a previously disabled startup entry without deleting it. Confirm-gated.",
        {"name": {"type": "string"}, "confirm": {"type": "boolean"}},
        ["name"],
    ),
    _tool(
        "procctl_startup_disable",
        "Disable a startup entry without removing it (Task-Manager style). Confirm-gated.",
        {"name": {"type": "string"}, "confirm": {"type": "boolean"}},
        ["name"],
    ),
    # -- BackgroundApps --
    _tool(
        "procctl_process_list",
        "List running processes sorted by memory or CPU usage.",
        {"sort_by": {"type": "string", "enum": ["memory", "cpu"]}, "top_n": {"type": "integer"}},
    ),
    _tool(
        "procctl_process_get_details",
        "Get full detail (status, CPU, memory, threads, path, cmdline) for one process by PID.",
        {"pid": {"type": "integer"}},
        ["pid"],
    ),
    _tool(
        "procctl_process_find",
        "Find running processes whose name contains the given (case-insensitive) string.",
        {"name": {"type": "string"}},
        ["name"],
    ),
    _tool(
        "procctl_process_kill",
        "End a running process by PID. Refuses outright for processes critical to the OS or to "
        "ULTRON's own session. Otherwise confirm-gated.",
        {"pid": {"type": "integer"}, "confirm": {"type": "boolean"}},
        ["pid"],
    ),
    # -- WindowsTaskScheduler --
    _tool(
        "procctl_task_list",
        "List native Windows Scheduled Tasks (name, path, state), optionally only enabled ones "
        "and/or filtered by task-path substring.",
        {"only_enabled": {"type": "boolean"}, "path_filter": {"type": "string"}},
    ),
    _tool(
        "procctl_task_get_info",
        "Get full detail for one Windows Scheduled Task: state, triggers, actions, last/next run.",
        {"task_name": {"type": "string"}, "task_path": {"type": "string"}},
        ["task_name"],
    ),
    _tool(
        "procctl_task_create",
        "Create a Windows Scheduled Task that runs a command on a trigger ('daily' at a given "
        "HH:MM time, or 'logon'). Runs as the current user. Confirm-gated.",
        {
            "name": {"type": "string"},
            "command": {"type": "string"},
            "arguments": {"type": "string"},
            "trigger_type": {"type": "string", "enum": ["daily", "logon"]},
            "time": {"type": "string"},
            "confirm": {"type": "boolean"},
        },
        ["name", "command"],
    ),
    _tool(
        "procctl_task_delete",
        "Delete a Windows Scheduled Task. Confirm-gated.",
        {"task_name": {"type": "string"}, "task_path": {"type": "string"}, "confirm": {"type": "boolean"}},
        ["task_name"],
    ),
    _tool(
        "procctl_task_enable",
        "Enable a disabled Windows Scheduled Task. Confirm-gated.",
        {"task_name": {"type": "string"}, "task_path": {"type": "string"}, "confirm": {"type": "boolean"}},
        ["task_name"],
    ),
    _tool(
        "procctl_task_disable",
        "Disable a Windows Scheduled Task without deleting it. Confirm-gated.",
        {"task_name": {"type": "string"}, "task_path": {"type": "string"}, "confirm": {"type": "boolean"}},
        ["task_name"],
    ),
    _tool(
        "procctl_task_run_now",
        "Trigger a Windows Scheduled Task to run immediately, outside its normal schedule. " "Confirm-gated.",
        {"task_name": {"type": "string"}, "task_path": {"type": "string"}, "confirm": {"type": "boolean"}},
        ["task_name"],
    ),
]

# ---------------------------------------------------------------------------
# Direct handlers - flat name -> lambda(args_dict) -> result dict
# ---------------------------------------------------------------------------
PROCESS_CONTROL_DIRECT_HANDLERS = {
    # -- StartupManager --
    "procctl_startup_list": lambda d, _k="startup_manager", _m="list_startup_items", _p=[]: getattr(_get(_k), _m)(
        **_pick(d, _p)
    ),
    "procctl_startup_add": lambda d, _k="startup_manager", _m="add_startup_item", _p=[
        "name",
        "command",
        "confirm",
    ]: getattr(_get(_k), _m)(**_pick(d, _p)),
    "procctl_startup_remove": lambda d, _k="startup_manager", _m="remove_startup_item", _p=["name", "confirm"]: getattr(
        _get(_k), _m
    )(**_pick(d, _p)),
    "procctl_startup_enable": lambda d, _k="startup_manager", _m="enable_startup_item", _p=["name", "confirm"]: getattr(
        _get(_k), _m
    )(**_pick(d, _p)),
    "procctl_startup_disable": lambda d, _k="startup_manager", _m="disable_startup_item", _p=[
        "name",
        "confirm",
    ]: getattr(_get(_k), _m)(**_pick(d, _p)),
    # -- BackgroundApps --
    "procctl_process_list": lambda d, _k="background_apps", _m="list_running_processes", _p=[
        "sort_by",
        "top_n",
    ]: getattr(_get(_k), _m)(**_pick(d, _p)),
    "procctl_process_get_details": lambda d, _k="background_apps", _m="get_process_details", _p=["pid"]: getattr(
        _get(_k), _m
    )(**_pick(d, _p)),
    "procctl_process_find": lambda d, _k="background_apps", _m="find_process", _p=["name"]: getattr(_get(_k), _m)(
        **_pick(d, _p)
    ),
    "procctl_process_kill": lambda d, _k="background_apps", _m="kill_process", _p=["pid", "confirm"]: getattr(
        _get(_k), _m
    )(**_pick(d, _p)),
    # -- WindowsTaskScheduler --
    "procctl_task_list": lambda d, _k="task_scheduler", _m="list_tasks", _p=["only_enabled", "path_filter"]: getattr(
        _get(_k), _m
    )(**_pick(d, _p)),
    "procctl_task_get_info": lambda d, _k="task_scheduler", _m="get_task_info", _p=["task_name", "task_path"]: getattr(
        _get(_k), _m
    )(**_pick(d, _p)),
    "procctl_task_create": lambda d, _k="task_scheduler", _m="create_task", _p=[
        "name",
        "command",
        "arguments",
        "trigger_type",
        "time",
        "confirm",
    ]: getattr(_get(_k), _m)(**_pick(d, _p)),
    "procctl_task_delete": lambda d, _k="task_scheduler", _m="delete_task", _p=[
        "task_name",
        "task_path",
        "confirm",
    ]: getattr(_get(_k), _m)(**_pick(d, _p)),
    "procctl_task_enable": lambda d, _k="task_scheduler", _m="enable_task", _p=[
        "task_name",
        "task_path",
        "confirm",
    ]: getattr(_get(_k), _m)(**_pick(d, _p)),
    "procctl_task_disable": lambda d, _k="task_scheduler", _m="disable_task", _p=[
        "task_name",
        "task_path",
        "confirm",
    ]: getattr(_get(_k), _m)(**_pick(d, _p)),
    "procctl_task_run_now": lambda d, _k="task_scheduler", _m="run_task_now", _p=[
        "task_name",
        "task_path",
        "confirm",
    ]: getattr(_get(_k), _m)(**_pick(d, _p)),
}
