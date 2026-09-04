"""
P3 Engine Tools
===============
Function-calling schema for the two P3 systems, same pattern as
ai/p1_engine_tools.py / ai/p2_engine_tools.py - local _tool() copy to
avoid a circular import with ai/tools_schema.py.

Backing implementations:
    intelligence/knowledge_os/          - remember_subject_fact .. search_knowledge
    intelligence/resource_intelligence/ - recommend_execution_tier ..
                                           get_resource_intelligence_report

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


P3_ENGINE_TOOLS = [
    # --- Unified Personal Knowledge OS --------------------------------------
    _tool(
        "remember_subject_fact",
        "Record a fact about a subject in the unified Knowledge OS, tagged by source. If another "
        "source already has a different fact for the same subject/predicate, the result will flag "
        "it as conflicting so it can be routed to the Conflict Resolution Engine.",
        {
            "subject": {"type": "string"},
            "fact_text": {"type": "string"},
            "predicate": {"type": "string", "description": "Defaults to 'is'"},
            "source": {"type": "string", "description": "Defaults to 'user'"},
            "confidence": {"type": "number", "description": "0.0 to 1.0, defaults to 0.8"},
        },
        ["subject", "fact_text"],
    ),
    _tool(
        "get_unified_knowledge_view",
        "Get everything Ultron knows about a subject, merged from the Knowledge OS's own ledger "
        "and (best-effort) the knowledge graph and semantic memory, in one tagged-by-source answer.",
        {"subject": {"type": "string"}},
        ["subject"],
    ),
    _tool(
        "search_knowledge",
        "Unified search across the Knowledge OS's own fact ledger and (best-effort) semantic memory.",
        {"query": {"type": "string"}, "limit": {"type": "integer", "description": "Default 20"}},
        ["query"],
    ),
    _tool(
        "get_knowledge_freshness_report",
        "List facts in the Knowledge OS's own ledger that are old enough to be worth re-confirming "
        "with the user rather than trusted as still current.",
        {"max_age_days": {"type": "number", "description": "Defaults to 7 days"}},
    ),
    # --- Resource-Aware Intelligence Engine -----------------------------------
    _tool(
        "recommend_execution_tier",
        "Before running a potentially heavy task, get a recommendation on how to run it - full "
        "local, a lighter local path, deferred until load drops, or cloud-offloaded - based on "
        "current system load and this task type's own historical cost.",
        {
            "task_type": {
                "type": "string",
                "description": "A stable label for this kind of task, e.g. 'research_topic'",
            },
            "estimated_cost": {"type": "string", "description": "low | medium | high"},
        },
        ["task_type"],
    ),
    _tool(
        "track_task_resource_cost",
        "Record the real measured cost of a task execution (duration and CPU/memory before/after) "
        "so future recommend_execution_tier calls for this task_type are better informed.",
        {
            "task_type": {"type": "string"},
            "duration_ms": {"type": "number"},
            "cpu_before": {"type": "number"},
            "cpu_after": {"type": "number"},
            "mem_before": {"type": "number"},
            "mem_after": {"type": "number"},
        },
        ["task_type", "duration_ms"],
    ),
    _tool(
        "get_resource_intelligence_report",
        "Get current system load plus the costliest known task types by average duration.",
    ),
]
