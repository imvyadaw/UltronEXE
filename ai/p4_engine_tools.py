"""
P4 Engine Tools
===============
Function-calling schema for the two P4 systems, same pattern as
ai/p1_engine_tools.py / ai/p2_engine_tools.py - local _tool() copy to
avoid a circular import with ai/tools_schema.py.

Backing implementations:
    ai/tool_benchmark/                  - record_tool_benchmark ..
                                           get_degrading_tools
    intelligence/conflict_resolution/   - detect_source_conflict ..
                                           get_conflict_report

Every name below must also exist in core/executor.py's tool_map.
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


P4_ENGINE_TOOLS = [
    # --- Automatic Tool Benchmarking & Reliability Scoring --------------------
    _tool(
        "record_tool_benchmark",
        "Manually log a timing/outcome sample for a tool call. Note: normally recorded "
        "automatically alongside tool_chain_optimizer's stats - use this only if a call needs to "
        "be logged another way.",
        {"tool_name": {"type": "string"}, "duration_ms": {"type": "number"}, "success": {"type": "boolean"}},
        ["tool_name", "duration_ms", "success"],
    ),
    _tool(
        "get_tool_benchmark",
        "Get real latency percentiles (p50/p95), success rate, and a degrading/stable/improving "
        "trend for a specific tool, based on its recent call history.",
        {"tool_name": {"type": "string"}},
        ["tool_name"],
    ),
    _tool(
        "get_tool_benchmark_report",
        "Get benchmark stats (latency, success rate, trend) across all tracked tools.",
        {"limit": {"type": "integer", "description": "Default 20"}},
    ),
    _tool(
        "get_degrading_tools",
        "List tools whose recent latency and success rate have both gotten meaningfully worse "
        "compared to their earlier history - worth investigating.",
    ),
    # --- Conflict Resolution Engine --------------------------------------------
    _tool(
        "detect_source_conflict",
        "Log a detected disagreement between two sources' claims about the same subject (e.g. "
        "calendar says one meeting time, email says another) so it can be tracked and resolved.",
        {
            "subject": {"type": "string"},
            "claim_a": {"type": "string"},
            "source_a": {"type": "string"},
            "claim_b": {"type": "string"},
            "source_b": {"type": "string"},
        },
        ["subject", "claim_a", "source_a", "claim_b", "source_b"],
    ),
    _tool(
        "auto_resolve_conflict",
        "Try to automatically resolve a logged conflict using each source's historical reliability "
        "score - only picks a winner when the reliability gap is clear enough; otherwise leaves it "
        "open for manual review.",
        {"conflict_id": {"type": "string"}},
        ["conflict_id"],
    ),
    _tool(
        "manual_resolve_conflict",
        "Manually resolve a logged conflict by choosing which source's claim to trust.",
        {"conflict_id": {"type": "string"}, "resolved_source": {"type": "string"}, "note": {"type": "string"}},
        ["conflict_id", "resolved_source"],
    ),
    _tool(
        "list_open_conflicts",
        "List currently unresolved detected conflicts, optionally filtered to one subject.",
        {"subject": {"type": "string"}},
    ),
    _tool(
        "get_conflict_report",
        "Get a summary of recent conflicts (open and resolved) with resolution history.",
        {"limit": {"type": "integer", "description": "Default 20"}},
    ),
]
