"""Special Control tool registry
=================================
Wires system_control/special/* (face recognition device control,
gesture-to-action bindings, predictive-action approval, unified
context snapshot + rules, self-optimization passes, emergency/panic
mode, habit-to-automation bridge, multi-user profile linking, scoped
remote-access grants) into the AI tool-calling loop. Same pattern as
ai/security_control_tools.py: lazy singletons + a flat
SPECIAL_CONTROL_TOOLS / SPECIAL_CONTROL_DIRECT_HANDLERS pair, merged
at the bottom of ai/tools_schema.py and ai/tool_runtime.py
respectively.

Naming: every tool is prefixed `specctl_`. Each underlying module's
own docstring spells out exactly which pre-existing subsystem it
delegates to (vision/face, vision/gestures, proactive/*, cognitive_core,
memory/habit_memory, memory/user, system_control/security /network) so
this registry never duplicates tools already exposed elsewhere under
different prefixes.

Every state-changing method on the underlying classes is confirm-gated
(confirm: bool, defaults False) - same pattern as every other
destructive tool in this codebase. Several of these (disabling remote
access lockdown aside, most others) increase capability/exposure
rather than reduce it, so the preview text spells out what starts
happening, not just the mechanical change.
"""

from typing import Dict


def _tool(name: str, description: str, properties: dict = None, required: list = None) -> dict:
    """Identical shape to ai/tools_schema.py's `_tool()` helper. Duplicated
    on purpose - avoids a circular import since tools_schema.py imports
    *from* this module."""
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

    if key == "face":
        from system_control.special.face_recognition import get_face_recognition_control

        obj = get_face_recognition_control()
    elif key == "gesture":
        from system_control.special.gesture_control import get_gesture_control

        obj = get_gesture_control()
    elif key == "predictive":
        from system_control.special.predictive_actions import get_predictive_actions_control

        obj = get_predictive_actions_control()
    elif key == "context":
        from system_control.special.context_awareness import get_context_awareness_control

        obj = get_context_awareness_control()
    elif key == "selfopt":
        from system_control.special.self_optimization import get_self_optimization_control

        obj = get_self_optimization_control()
    elif key == "emergency":
        from system_control.special.emergency_mode import get_emergency_mode_control

        obj = get_emergency_mode_control()
    elif key == "habit":
        from system_control.special.habit_learning import get_habit_learning_control

        obj = get_habit_learning_control()
    elif key == "multiuser":
        from system_control.special.multi_user_profiles import get_multi_user_profiles_control

        obj = get_multi_user_profiles_control()
    elif key == "remote":
        from system_control.special.remote_access import get_remote_access_control

        obj = get_remote_access_control()
    else:
        raise KeyError(f"Unknown special_control tool key: {key}")

    _instances[key] = obj
    return obj


# ---------------------------------------------------------------------------
# Tool schemas
# ---------------------------------------------------------------------------
SPECIAL_CONTROL_TOOLS = [
    # -- FaceRecognitionControl --
    _tool("specctl_face_list_cameras", "List camera devices via PnP."),
    _tool("specctl_face_get_camera_privacy", "Get whether apps are allowed to use the camera."),
    _tool(
        "specctl_face_set_camera_privacy",
        "Allow or block apps from using the camera. Confirm-gated.",
        {"allowed": {"type": "boolean"}, "confirm": {"type": "boolean"}},
        ["allowed"],
    ),
    _tool(
        "specctl_face_capture_and_identify",
        "Capture a webcam frame and identify it against the general or unlock-specific face store.",
        {"camera_index": {"type": "integer"}, "use_lock_store": {"type": "boolean"}},
    ),
    _tool(
        "specctl_face_enroll",
        "Enroll a new face from the webcam. Confirm-gated.",
        {
            "name": {"type": "string"},
            "camera_index": {"type": "integer"},
            "for_unlock": {"type": "boolean"},
            "confirm": {"type": "boolean"},
        },
        ["name"],
    ),
    _tool("specctl_face_list_known", "List known faces in both the general and unlock-specific stores."),
    _tool(
        "specctl_face_set_unknown_face_policy",
        "Set the policy for an unrecognized face: 'ignore', 'notify', or 'lock_workstation'. Confirm-gated.",
        {"action": {"type": "string"}, "confirm": {"type": "boolean"}},
        ["action"],
    ),
    _tool("specctl_face_get_unknown_face_policy", "Get the current unknown-face policy."),
    # -- GestureControl --
    _tool("specctl_gesture_list_available_gestures", "List gestures the recognizer can classify."),
    _tool("specctl_gesture_list_available_actions", "List system actions a gesture can be bound to."),
    _tool("specctl_gesture_list_bindings", "List current gesture-to-action bindings."),
    _tool(
        "specctl_gesture_bind",
        "Bind a gesture to a system action. Confirm-gated.",
        {"gesture": {"type": "string"}, "action": {"type": "string"}, "confirm": {"type": "boolean"}},
        ["gesture", "action"],
    ),
    _tool(
        "specctl_gesture_unbind",
        "Remove a gesture binding. Confirm-gated.",
        {"gesture": {"type": "string"}, "confirm": {"type": "boolean"}},
        ["gesture"],
    ),
    _tool("specctl_gesture_process_frame", "Detect a gesture from the webcam and execute its bound action if enabled."),
    _tool(
        "specctl_gesture_set_enabled",
        "Enable or disable gesture-driven system actions. Confirm-gated.",
        {"enabled": {"type": "boolean"}, "confirm": {"type": "boolean"}},
        ["enabled"],
    ),
    _tool("specctl_gesture_get_status", "Get whether gesture control is enabled and current bindings."),
    # -- PredictiveActionsControl --
    _tool(
        "specctl_predictive_get_predictions",
        "Get the top predicted next actions.",
        {"context": {"type": "object"}, "top_k": {"type": "integer"}},
    ),
    _tool(
        "specctl_predictive_get_routine_prediction",
        "Get a routine (time-based) prediction if confident enough.",
        {"min_confidence": {"type": "number"}},
    ),
    _tool(
        "specctl_predictive_get_suggestions",
        "Get human-phrased action suggestions, tagged with auto-execute eligibility.",
        {"context": {"type": "object"}, "top_k": {"type": "integer"}},
    ),
    _tool(
        "specctl_predictive_approve_and_execute",
        "Run one suggestion right now.",
        {"suggestion": {"type": "object"}},
        ["suggestion"],
    ),
    _tool(
        "specctl_predictive_dismiss",
        "Dismiss/disallow an action from auto-executing.",
        {"action_name": {"type": "string"}},
        ["action_name"],
    ),
    _tool(
        "specctl_predictive_set_auto_execute_for_action",
        "Allow or disallow an action to auto-execute without asking. Confirm-gated.",
        {"action_name": {"type": "string"}, "allowed": {"type": "boolean"}, "confirm": {"type": "boolean"}},
        ["action_name", "allowed"],
    ),
    _tool("specctl_predictive_list_auto_execute_actions", "List actions currently allowed to auto-execute."),
    _tool("specctl_predictive_get_auto_execute_threshold", "Get the current auto-execute confidence threshold."),
    _tool(
        "specctl_predictive_set_auto_execute_threshold",
        "Set the auto-execute confidence threshold (0.0-1.0). Confirm-gated.",
        {"threshold": {"type": "number"}, "confirm": {"type": "boolean"}},
        ["threshold"],
    ),
    # -- ContextAwarenessControl --
    _tool(
        "specctl_context_get_snapshot",
        "Get a unified snapshot of activity, system health, network, and cognitive context.",
    ),
    _tool("specctl_context_list_rules", "List context-based automation rules."),
    _tool(
        "specctl_context_add_rule",
        "Add a rule: when the foreground window matches a pattern, run an action. Confirm-gated.",
        {
            "name": {"type": "string"},
            "window_title_pattern": {"type": "string"},
            "action": {"type": "string"},
            "enabled": {"type": "boolean"},
            "confirm": {"type": "boolean"},
        },
        ["name", "window_title_pattern", "action"],
    ),
    _tool(
        "specctl_context_remove_rule",
        "Remove a context rule. Confirm-gated.",
        {"name": {"type": "string"}, "confirm": {"type": "boolean"}},
        ["name"],
    ),
    _tool(
        "specctl_context_set_rule_enabled",
        "Enable or disable a context rule. Confirm-gated.",
        {"name": {"type": "string"}, "enabled": {"type": "boolean"}, "confirm": {"type": "boolean"}},
        ["name", "enabled"],
    ),
    _tool(
        "specctl_context_evaluate_and_apply",
        "Check the current foreground window against enabled rules and apply the first match.",
    ),
    # -- SelfOptimizationControl --
    _tool("specctl_selfopt_get_power_plan", "Get the active Windows power plan."),
    _tool(
        "specctl_selfopt_set_power_plan",
        "Set the active power plan: 'power_saver', 'balanced', or 'high_performance'. Confirm-gated.",
        {"plan": {"type": "string"}, "confirm": {"type": "boolean"}},
        ["plan"],
    ),
    _tool(
        "specctl_selfopt_get_top_consumers", "Get the top resource-consuming processes.", {"limit": {"type": "integer"}}
    ),
    _tool(
        "specctl_selfopt_trim_process",
        "Kill a background process by PID. Confirm-gated.",
        {"pid": {"type": "integer"}, "confirm": {"type": "boolean"}},
        ["pid"],
    ),
    _tool("specctl_selfopt_get_startup_impact", "List startup items and their impact."),
    _tool(
        "specctl_selfopt_disable_startup_item",
        "Disable a startup item. Confirm-gated.",
        {"name": {"type": "string"}, "confirm": {"type": "boolean"}},
        ["name"],
    ),
    _tool(
        "specctl_selfopt_boost_priority",
        "Raise ULTRON's own process priority to Above Normal. Confirm-gated.",
        {"confirm": {"type": "boolean"}},
    ),
    _tool(
        "specctl_selfopt_run_pass",
        "Run a chained optimization pass: kill top background processes, disable startup items, switch power plan. Confirm-gated.",
        {
            "kill_top_n_background": {"type": "integer"},
            "disable_startup_items": {"type": "array", "items": {"type": "string"}},
            "target_power_plan": {"type": "string"},
            "confirm": {"type": "boolean"},
        },
    ),
    # -- EmergencyModeControl --
    _tool(
        "specctl_emergency_get_incident_log",
        "Get recent emergency-mode incident log entries.",
        {"limit": {"type": "integer"}},
    ),
    _tool(
        "specctl_emergency_trigger",
        "Trigger emergency/panic mode: lock workstation, snapshot webcam, cut remote access, optionally BitLocker-lock a drive, alert a contact. Confirm-gated.",
        {
            "reason": {"type": "string"},
            "lock_workstation": {"type": "boolean"},
            "snapshot_webcam": {"type": "boolean"},
            "lock_remote_access": {"type": "boolean"},
            "lock_bitlocker_drive": {"type": "string"},
            "alert_phone": {"type": "string"},
            "confirm": {"type": "boolean"},
        },
    ),
    _tool("specctl_emergency_get_status", "Get whether emergency mode is currently active."),
    _tool(
        "specctl_emergency_exit",
        "Exit emergency mode, optionally restoring remote access. Confirm-gated.",
        {"restore_remote_access": {"type": "boolean"}, "confirm": {"type": "boolean"}},
    ),
    # -- HabitLearningControl --
    _tool(
        "specctl_habit_record_action",
        "Record an observed action for habit detection.",
        {"action": {"type": "string"}, "context": {"type": "string"}},
        ["action"],
    ),
    _tool(
        "specctl_habit_get_detected", "Get detected repeated-action habits.", {"min_occurrences": {"type": "integer"}}
    ),
    _tool(
        "specctl_habit_get_confidence",
        "Get the habit confidence score for an action.",
        {"action": {"type": "string"}},
        ["action"],
    ),
    _tool(
        "specctl_habit_suggest_automation",
        "Turn a detected habit into a proposed automation pipeline.",
        {"habit": {"type": "object"}},
        ["habit"],
    ),
    _tool(
        "specctl_habit_create_automation",
        "Create a scheduled automation pipeline from a habit. Confirm-gated.",
        {
            "pipeline_name": {"type": "string"},
            "steps": {"type": "array", "items": {"type": "object"}},
            "confirm": {"type": "boolean"},
        },
        ["pipeline_name", "steps"],
    ),
    _tool(
        "specctl_habit_run_automation",
        "Run a habit-derived automation pipeline. Confirm-gated.",
        {"pipeline_name": {"type": "string"}, "confirm": {"type": "boolean"}},
        ["pipeline_name"],
    ),
    _tool("specctl_habit_list_automations", "List habit-derived automation pipelines."),
    _tool(
        "specctl_habit_clear_history",
        "Delete all recorded history for an action. Confirm-gated.",
        {"action": {"type": "string"}, "confirm": {"type": "boolean"}},
        ["action"],
    ),
    # -- MultiUserProfilesControl --
    _tool("specctl_multiuser_list_os_accounts", "List Windows OS accounts."),
    _tool(
        "specctl_multiuser_link_account",
        "Link a Windows account to a ULTRON profile. Confirm-gated.",
        {"windows_username": {"type": "string"}, "profile_id": {"type": "string"}, "confirm": {"type": "boolean"}},
        ["windows_username", "profile_id"],
    ),
    _tool(
        "specctl_multiuser_unlink_account",
        "Unlink a Windows account from its ULTRON profile. Confirm-gated.",
        {"windows_username": {"type": "string"}, "confirm": {"type": "boolean"}},
        ["windows_username"],
    ),
    _tool("specctl_multiuser_list_links", "List Windows-account-to-ULTRON-profile links."),
    _tool("specctl_multiuser_get_active_profile", "Get the currently active ULTRON profile."),
    _tool(
        "specctl_multiuser_set_active_profile",
        "Set the active ULTRON profile. Confirm-gated.",
        {"profile_id": {"type": "string"}, "confirm": {"type": "boolean"}},
        ["profile_id"],
    ),
    _tool(
        "specctl_multiuser_activate_for_account",
        "Activate the ULTRON profile linked to a Windows account. Confirm-gated.",
        {"windows_username": {"type": "string"}, "confirm": {"type": "boolean"}},
        ["windows_username"],
    ),
    _tool(
        "specctl_multiuser_get_active_profile_traits",
        "Get traits for the active ULTRON profile.",
        {"min_confidence": {"type": "number"}},
    ),
    _tool(
        "specctl_multiuser_switch_windows_account",
        "Fast-switch the active Windows session to another account. Confirm-gated.",
        {"windows_username": {"type": "string"}, "confirm": {"type": "boolean"}},
        ["windows_username"],
    ),
    # -- RemoteAccessControl --
    _tool("specctl_remote_get_status", "Get RDP/SSH status and any active scoped access grant."),
    _tool("specctl_remote_get_grant_status", "Get the current scoped remote-access grant status."),
    _tool(
        "specctl_remote_grant_temporary_access",
        "Grant temporary RDP/SSH access scoped to one IP, auto-revoked after a duration. Confirm-gated.",
        {
            "allowed_ip": {"type": "string"},
            "duration_minutes": {"type": "integer"},
            "enable_rdp": {"type": "boolean"},
            "enable_ssh": {"type": "boolean"},
            "confirm": {"type": "boolean"},
        },
        ["allowed_ip"],
    ),
    _tool(
        "specctl_remote_extend_grant",
        "Extend the current remote-access grant. Confirm-gated.",
        {"additional_minutes": {"type": "integer"}, "confirm": {"type": "boolean"}},
        ["additional_minutes"],
    ),
    _tool(
        "specctl_remote_revoke_all",
        "Disable RDP/SSH and remove the scoped firewall rule. Confirm-gated.",
        {"confirm": {"type": "boolean"}},
    ),
    _tool(
        "specctl_remote_emergency_lockdown",
        "Immediately cut off all remote access. Confirm-gated.",
        {"confirm": {"type": "boolean"}},
    ),
]


# ---------------------------------------------------------------------------
# Direct handlers
# ---------------------------------------------------------------------------
SPECIAL_CONTROL_DIRECT_HANDLERS = {
    # -- FaceRecognitionControl --
    "specctl_face_list_cameras": lambda d, _k="face", _m="list_cameras", _p=[]: getattr(_get(_k), _m)(**_pick(d, _p)),
    "specctl_face_get_camera_privacy": lambda d, _k="face", _m="get_camera_privacy_status", _p=[]: getattr(
        _get(_k), _m
    )(**_pick(d, _p)),
    "specctl_face_set_camera_privacy": lambda d, _k="face", _m="set_camera_privacy", _p=["allowed", "confirm"]: getattr(
        _get(_k), _m
    )(**_pick(d, _p)),
    "specctl_face_capture_and_identify": lambda d, _k="face", _m="capture_and_identify", _p=[
        "camera_index",
        "use_lock_store",
    ]: getattr(_get(_k), _m)(**_pick(d, _p)),
    "specctl_face_enroll": lambda d, _k="face", _m="enroll_face", _p=[
        "name",
        "camera_index",
        "for_unlock",
        "confirm",
    ]: getattr(_get(_k), _m)(**_pick(d, _p)),
    "specctl_face_list_known": lambda d, _k="face", _m="list_known_faces", _p=[]: getattr(_get(_k), _m)(**_pick(d, _p)),
    "specctl_face_set_unknown_face_policy": lambda d, _k="face", _m="set_unknown_face_policy", _p=[
        "action",
        "confirm",
    ]: getattr(_get(_k), _m)(**_pick(d, _p)),
    "specctl_face_get_unknown_face_policy": lambda d, _k="face", _m="get_unknown_face_policy", _p=[]: getattr(
        _get(_k), _m
    )(**_pick(d, _p)),
    # -- GestureControl --
    "specctl_gesture_list_available_gestures": lambda d, _k="gesture", _m="list_available_gestures", _p=[]: getattr(
        _get(_k), _m
    )(**_pick(d, _p)),
    "specctl_gesture_list_available_actions": lambda d, _k="gesture", _m="list_available_actions", _p=[]: getattr(
        _get(_k), _m
    )(**_pick(d, _p)),
    "specctl_gesture_list_bindings": lambda d, _k="gesture", _m="list_bindings", _p=[]: getattr(_get(_k), _m)(
        **_pick(d, _p)
    ),
    "specctl_gesture_bind": lambda d, _k="gesture", _m="bind_gesture", _p=["gesture", "action", "confirm"]: getattr(
        _get(_k), _m
    )(**_pick(d, _p)),
    "specctl_gesture_unbind": lambda d, _k="gesture", _m="unbind_gesture", _p=["gesture", "confirm"]: getattr(
        _get(_k), _m
    )(**_pick(d, _p)),
    "specctl_gesture_process_frame": lambda d, _k="gesture", _m="process_frame", _p=[]: getattr(_get(_k), _m)(
        **_pick(d, _p)
    ),
    "specctl_gesture_set_enabled": lambda d, _k="gesture", _m="set_enabled", _p=["enabled", "confirm"]: getattr(
        _get(_k), _m
    )(**_pick(d, _p)),
    "specctl_gesture_get_status": lambda d, _k="gesture", _m="get_status", _p=[]: getattr(_get(_k), _m)(**_pick(d, _p)),
    # -- PredictiveActionsControl --
    "specctl_predictive_get_predictions": lambda d, _k="predictive", _m="get_predictions", _p=[
        "context",
        "top_k",
    ]: getattr(_get(_k), _m)(**_pick(d, _p)),
    "specctl_predictive_get_routine_prediction": lambda d, _k="predictive", _m="get_routine_prediction", _p=[
        "min_confidence"
    ]: getattr(_get(_k), _m)(**_pick(d, _p)),
    "specctl_predictive_get_suggestions": lambda d, _k="predictive", _m="get_suggestions", _p=[
        "context",
        "top_k",
    ]: getattr(_get(_k), _m)(**_pick(d, _p)),
    "specctl_predictive_approve_and_execute": lambda d, _k="predictive", _m="approve_and_execute", _p=[
        "suggestion"
    ]: getattr(_get(_k), _m)(**_pick(d, _p)),
    "specctl_predictive_dismiss": lambda d, _k="predictive", _m="dismiss", _p=["action_name"]: getattr(_get(_k), _m)(
        **_pick(d, _p)
    ),
    "specctl_predictive_set_auto_execute_for_action": lambda d, _k="predictive", _m="set_auto_execute_for_action", _p=[
        "action_name",
        "allowed",
        "confirm",
    ]: getattr(_get(_k), _m)(**_pick(d, _p)),
    "specctl_predictive_list_auto_execute_actions": lambda d, _k="predictive", _m="list_auto_execute_actions", _p=[]: getattr(
        _get(_k), _m
    )(
        **_pick(d, _p)
    ),
    "specctl_predictive_get_auto_execute_threshold": lambda d, _k="predictive", _m="get_auto_execute_threshold", _p=[]: getattr(
        _get(_k), _m
    )(
        **_pick(d, _p)
    ),
    "specctl_predictive_set_auto_execute_threshold": lambda d, _k="predictive", _m="set_auto_execute_threshold", _p=[
        "threshold",
        "confirm",
    ]: getattr(_get(_k), _m)(**_pick(d, _p)),
    # -- ContextAwarenessControl --
    "specctl_context_get_snapshot": lambda d, _k="context", _m="get_snapshot", _p=[]: getattr(_get(_k), _m)(
        **_pick(d, _p)
    ),
    "specctl_context_list_rules": lambda d, _k="context", _m="list_rules", _p=[]: getattr(_get(_k), _m)(**_pick(d, _p)),
    "specctl_context_add_rule": lambda d, _k="context", _m="add_rule", _p=[
        "name",
        "window_title_pattern",
        "action",
        "enabled",
        "confirm",
    ]: getattr(_get(_k), _m)(**_pick(d, _p)),
    "specctl_context_remove_rule": lambda d, _k="context", _m="remove_rule", _p=["name", "confirm"]: getattr(
        _get(_k), _m
    )(**_pick(d, _p)),
    "specctl_context_set_rule_enabled": lambda d, _k="context", _m="set_rule_enabled", _p=[
        "name",
        "enabled",
        "confirm",
    ]: getattr(_get(_k), _m)(**_pick(d, _p)),
    "specctl_context_evaluate_and_apply": lambda d, _k="context", _m="evaluate_and_apply", _p=[]: getattr(_get(_k), _m)(
        **_pick(d, _p)
    ),
    # -- SelfOptimizationControl --
    "specctl_selfopt_get_power_plan": lambda d, _k="selfopt", _m="get_active_power_plan", _p=[]: getattr(_get(_k), _m)(
        **_pick(d, _p)
    ),
    "specctl_selfopt_set_power_plan": lambda d, _k="selfopt", _m="set_power_plan", _p=["plan", "confirm"]: getattr(
        _get(_k), _m
    )(**_pick(d, _p)),
    "specctl_selfopt_get_top_consumers": lambda d, _k="selfopt", _m="get_top_resource_consumers", _p=["limit"]: getattr(
        _get(_k), _m
    )(**_pick(d, _p)),
    "specctl_selfopt_trim_process": lambda d, _k="selfopt", _m="trim_background_process", _p=[
        "pid",
        "confirm",
    ]: getattr(_get(_k), _m)(**_pick(d, _p)),
    "specctl_selfopt_get_startup_impact": lambda d, _k="selfopt", _m="get_startup_impact", _p=[]: getattr(_get(_k), _m)(
        **_pick(d, _p)
    ),
    "specctl_selfopt_disable_startup_item": lambda d, _k="selfopt", _m="disable_startup_item", _p=[
        "name",
        "confirm",
    ]: getattr(_get(_k), _m)(**_pick(d, _p)),
    "specctl_selfopt_boost_priority": lambda d, _k="selfopt", _m="boost_ultron_priority", _p=["confirm"]: getattr(
        _get(_k), _m
    )(**_pick(d, _p)),
    "specctl_selfopt_run_pass": lambda d, _k="selfopt", _m="run_optimization_pass", _p=[
        "kill_top_n_background",
        "disable_startup_items",
        "target_power_plan",
        "confirm",
    ]: getattr(_get(_k), _m)(**_pick(d, _p)),
    # -- EmergencyModeControl --
    "specctl_emergency_get_incident_log": lambda d, _k="emergency", _m="get_incident_log", _p=["limit"]: getattr(
        _get(_k), _m
    )(**_pick(d, _p)),
    "specctl_emergency_trigger": lambda d, _k="emergency", _m="trigger", _p=[
        "reason",
        "lock_workstation",
        "snapshot_webcam",
        "lock_remote_access",
        "lock_bitlocker_drive",
        "alert_phone",
        "confirm",
    ]: getattr(_get(_k), _m)(**_pick(d, _p)),
    "specctl_emergency_get_status": lambda d, _k="emergency", _m="get_status", _p=[]: getattr(_get(_k), _m)(
        **_pick(d, _p)
    ),
    "specctl_emergency_exit": lambda d, _k="emergency", _m="exit_emergency_mode", _p=[
        "restore_remote_access",
        "confirm",
    ]: getattr(_get(_k), _m)(**_pick(d, _p)),
    # -- HabitLearningControl --
    "specctl_habit_record_action": lambda d, _k="habit", _m="record_action", _p=["action", "context"]: getattr(
        _get(_k), _m
    )(**_pick(d, _p)),
    "specctl_habit_get_detected": lambda d, _k="habit", _m="get_detected_habits", _p=["min_occurrences"]: getattr(
        _get(_k), _m
    )(**_pick(d, _p)),
    "specctl_habit_get_confidence": lambda d, _k="habit", _m="get_habit_confidence", _p=["action"]: getattr(
        _get(_k), _m
    )(**_pick(d, _p)),
    "specctl_habit_suggest_automation": lambda d, _k="habit", _m="suggest_automation_for_habit", _p=["habit"]: getattr(
        _get(_k), _m
    )(**_pick(d, _p)),
    "specctl_habit_create_automation": lambda d, _k="habit", _m="create_automation_from_habit", _p=[
        "pipeline_name",
        "steps",
        "confirm",
    ]: getattr(_get(_k), _m)(**_pick(d, _p)),
    "specctl_habit_run_automation": lambda d, _k="habit", _m="run_habit_automation", _p=[
        "pipeline_name",
        "confirm",
    ]: getattr(_get(_k), _m)(**_pick(d, _p)),
    "specctl_habit_list_automations": lambda d, _k="habit", _m="list_habit_automations", _p=[]: getattr(_get(_k), _m)(
        **_pick(d, _p)
    ),
    "specctl_habit_clear_history": lambda d, _k="habit", _m="clear_habit_history", _p=["action", "confirm"]: getattr(
        _get(_k), _m
    )(**_pick(d, _p)),
    # -- MultiUserProfilesControl --
    "specctl_multiuser_list_os_accounts": lambda d, _k="multiuser", _m="list_os_accounts", _p=[]: getattr(_get(_k), _m)(
        **_pick(d, _p)
    ),
    "specctl_multiuser_link_account": lambda d, _k="multiuser", _m="link_account_to_profile", _p=[
        "windows_username",
        "profile_id",
        "confirm",
    ]: getattr(_get(_k), _m)(**_pick(d, _p)),
    "specctl_multiuser_unlink_account": lambda d, _k="multiuser", _m="unlink_account", _p=[
        "windows_username",
        "confirm",
    ]: getattr(_get(_k), _m)(**_pick(d, _p)),
    "specctl_multiuser_list_links": lambda d, _k="multiuser", _m="list_links", _p=[]: getattr(_get(_k), _m)(
        **_pick(d, _p)
    ),
    "specctl_multiuser_get_active_profile": lambda d, _k="multiuser", _m="get_active_profile", _p=[]: getattr(
        _get(_k), _m
    )(**_pick(d, _p)),
    "specctl_multiuser_set_active_profile": lambda d, _k="multiuser", _m="set_active_profile", _p=[
        "profile_id",
        "confirm",
    ]: getattr(_get(_k), _m)(**_pick(d, _p)),
    "specctl_multiuser_activate_for_account": lambda d, _k="multiuser", _m="activate_profile_for_windows_account", _p=[
        "windows_username",
        "confirm",
    ]: getattr(_get(_k), _m)(**_pick(d, _p)),
    "specctl_multiuser_get_active_profile_traits": lambda d, _k="multiuser", _m="get_active_profile_traits", _p=[
        "min_confidence"
    ]: getattr(_get(_k), _m)(**_pick(d, _p)),
    "specctl_multiuser_switch_windows_account": lambda d, _k="multiuser", _m="switch_windows_account", _p=[
        "windows_username",
        "confirm",
    ]: getattr(_get(_k), _m)(**_pick(d, _p)),
    # -- RemoteAccessControl --
    "specctl_remote_get_status": lambda d, _k="remote", _m="get_status", _p=[]: getattr(_get(_k), _m)(**_pick(d, _p)),
    "specctl_remote_get_grant_status": lambda d, _k="remote", _m="get_grant_status", _p=[]: getattr(_get(_k), _m)(
        **_pick(d, _p)
    ),
    "specctl_remote_grant_temporary_access": lambda d, _k="remote", _m="grant_temporary_access", _p=[
        "allowed_ip",
        "duration_minutes",
        "enable_rdp",
        "enable_ssh",
        "confirm",
    ]: getattr(_get(_k), _m)(**_pick(d, _p)),
    "specctl_remote_extend_grant": lambda d, _k="remote", _m="extend_grant", _p=[
        "additional_minutes",
        "confirm",
    ]: getattr(_get(_k), _m)(**_pick(d, _p)),
    "specctl_remote_revoke_all": lambda d, _k="remote", _m="revoke_all", _p=["confirm"]: getattr(_get(_k), _m)(
        **_pick(d, _p)
    ),
    "specctl_remote_emergency_lockdown": lambda d, _k="remote", _m="emergency_lockdown", _p=["confirm"]: getattr(
        _get(_k), _m
    )(**_pick(d, _p)),
}
