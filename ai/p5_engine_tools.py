"""
P5 Engine Tools
===============
Function-calling schema for the P5 system, same pattern as
ai/p1_engine_tools.py / ai/p2_engine_tools.py - local _tool() copy to
avoid a circular import with ai/tools_schema.py.

Backing implementation:
    intelligence/workflow_graph/ - register_workflow_graph_node ..
                                    get_workflow_graph_summary

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


P5_ENGINE_TOOLS = [
    # --- Personal Workflow Graph & Automation Discovery -------------------------
    _tool(
        "register_workflow_graph_node",
        "Register a named workflow and the ordered list of tools it uses into the personal "
        "workflow graph, so it can be connected to other workflows and considered for automation.",
        {
            "name": {"type": "string"},
            "tools_used": {"type": "array", "items": {"type": "string"}},
        },
        ["name", "tools_used"],
    ),
    _tool(
        "link_workflow_sequence",
        "Record that one workflow tends to be followed by another (each observation strengthens "
        "the link's weight), so repeated sequences can later be surfaced as automation candidates.",
        {"workflow_a": {"type": "string"}, "workflow_b": {"type": "string"}},
        ["workflow_a", "workflow_b"],
    ),
    _tool(
        "discover_automation_opportunities",
        "Scan the personal workflow graph (importing any newly detected repeating action patterns "
        "first) for tool/workflow sequences that repeat often enough to be worth chaining into a "
        "single automation.",
        {"min_weight": {"type": "number", "description": "Minimum observed-sequence weight, default 2"}},
    ),
    _tool(
        "get_workflow_graph_neighbors",
        "Get the tools a named workflow uses and which other workflows tend to follow it.",
        {"name": {"type": "string"}},
        ["name"],
    ),
    _tool(
        "get_workflow_graph_summary",
        "Get counts of workflows/tools/connections tracked in the personal workflow graph plus its "
        "strongest connections.",
    ),
]
