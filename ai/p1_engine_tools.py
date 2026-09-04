"""
P1 Engine Tools
===============
Function-calling schema for the three P1 systems, kept in its own file
following the same pattern as ai/phase30_extended_tools.py (local
_tool() copy to avoid a circular import with ai/tools_schema.py, which
imports P1_ENGINE_TOOLS and appends it to TOOLS).

Backing implementations:
    intelligence/mission_engine/   - create_mission .. abandon_mission
    ai/tool_chain_optimizer.py     - rank_tool_candidates, optimize_tool_chain,
                                      get_tool_reliability_report
    security/capability_isolation.py - check_capability_access,
                                        set_isolation_profile,
                                        get_isolation_policy,
                                        set_capability_scope_policy

Every name below must also exist in core/executor.py's tool_map -
that's where these actually dispatch.
"""


def _tool(name: str, description: str, properties: dict = None, required: list = None) -> dict:
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


P1_ENGINE_TOOLS = [
    # --- Mission Persistence Engine --------------------------------------
    _tool(
        "create_mission",
        "Start tracking a long-running, multi-session user objective (a 'mission') that should "
        "survive Ultron restarting - e.g. planning a trip, a multi-day project, tax filing. Use "
        "this for things bigger than a single-session task; for a quick single task, don't bother.",
        {
            "title": {"type": "string", "description": "Short mission title, e.g. 'Plan the Bangalore trip'"},
            "description": {"type": "string", "description": "Optional longer description"},
        },
        ["title"],
    ),
    _tool(
        "checkpoint_mission",
        "Save a point-in-time progress note on an active mission (a decision made, a step "
        "finished, info gathered) so it can be resumed with full context later or after a restart.",
        {
            "mission_id": {"type": "string"},
            "note": {"type": "string", "description": "Human-readable summary of what just happened"},
        },
        ["mission_id", "note"],
    ),
    _tool(
        "list_active_missions",
        "List all currently active (not paused/completed/abandoned) missions.",
    ),
    _tool(
        "get_resumable_mission",
        "Check whether there is a mission from a previous session worth resuming (idle long enough "
        "to plausibly be 'the thing from last time'). Call this near the start of a conversation.",
    ),
    _tool(
        "resume_mission",
        "Resume a specific mission by id, marking it active again and returning its recent checkpoints.",
        {"mission_id": {"type": "string"}},
        ["mission_id"],
    ),
    _tool(
        "pause_mission",
        "Pause an active mission without abandoning it.",
        {"mission_id": {"type": "string"}},
        ["mission_id"],
    ),
    _tool(
        "complete_mission",
        "Mark a mission as completed.",
        {"mission_id": {"type": "string"}},
        ["mission_id"],
    ),
    _tool(
        "abandon_mission",
        "Mark a mission as abandoned (user no longer wants to pursue it).",
        {"mission_id": {"type": "string"}},
        ["mission_id"],
    ),
    # --- Intelligent Tool-Chain Optimizer ---------------------------------
    _tool(
        "rank_tool_candidates",
        "Given several tools that could all accomplish the same sub-task (e.g. two different search "
        "backends), rank them best-first by real historical reliability on this install.",
        {"candidates": {"type": "array", "items": {"type": "string"}, "description": "Tool names to rank"}},
        ["candidates"],
    ),
    _tool(
        "optimize_tool_chain",
        "Given a planned sequence of tool names whose relative order is flexible, get a reliability-"
        "informed suggested order plus warnings about any historically unreliable tool in the chain.",
        {"tools": {"type": "array", "items": {"type": "string"}}},
        ["tools"],
    ),
    _tool(
        "get_tool_reliability_report",
        "Get a reliability report (success rate, avg latency, composite score) for the most-used tools.",
        {"limit": {"type": "integer", "description": "Max tools to return, default 20"}},
    ),
    # --- Capability Isolation / Fine-Grained Permissions -------------------
    _tool(
        "check_capability_access",
        "Check whether a tool call would be allowed, ask-gated, or denied under the current "
        "capability isolation profile, without actually running it.",
        {
            "tool_name": {"type": "string"},
            "arguments": {"type": "object", "description": "The arguments that would be passed to the tool"},
        },
        ["tool_name"],
    ),
    _tool(
        "set_isolation_profile",
        "Switch the active capability isolation profile (e.g. 'default', 'guest', 'locked_down'), "
        "changing which scopes (filesystem, network, shell, communication, etc.) are allowed/ask/denied.",
        {"profile": {"type": "string"}},
        ["profile"],
    ),
    _tool(
        "get_isolation_policy",
        "Get the scope policy (allow/ask/deny per scope) for a capability isolation profile.",
        {"profile": {"type": "string", "description": "Defaults to the currently active profile"}},
    ),
    _tool(
        "set_capability_scope_policy",
        "Set the allow/ask/deny mode for one scope within one isolation profile.",
        {
            "profile": {"type": "string"},
            "scope": {
                "type": "string",
                "description": "One of: filesystem_read, filesystem_write, network, "
                "shell_exec, system_control, communication_send, "
                "automation_ui, media_control, financial, unknown",
            },
            "mode": {"type": "string", "description": "allow | ask | deny"},
        },
        ["profile", "scope", "mode"],
    ),
]
