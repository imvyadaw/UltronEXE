"""
P2 Engine Tools
===============
Function-calling schema for the two P2 systems. Same pattern as
ai/p1_engine_tools.py - local _tool() copy to avoid a circular import
with ai/tools_schema.py.

Backing implementations:
    intelligence/evidence_ledger/       - log_claim_check .. get_untrustworthy_sources
    learning_engine/failure_pattern_engine.py - check_tool_failure_risk,
                                                 get_failure_patterns,
                                                 get_failure_pattern_report

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


P2_ENGINE_TOOLS = [
    # --- Evidence Ledger & Confidence Tracking -----------------------------
    _tool(
        "log_claim_check",
        "Manually log a claim you checked/verified along with its verdict, confidence, and evidence, "
        "so it's remembered for later ('why did you believe X') and feeds source reliability tracking. "
        "Note: check_fact already does this automatically - use this only for claims checked another way.",
        {
            "claim": {"type": "string"},
            "verdict": {"type": "string", "description": "supported | weakly_supported | unverified | contradicted"},
            "confidence": {"type": "number", "description": "0.0 to 1.0"},
            "evidence": {
                "type": "array",
                "items": {"type": "object"},
                "description": "List of {source, snippet, relevance}",
            },
            "context": {"type": "string"},
        },
        ["claim", "verdict", "confidence"],
    ),
    _tool(
        "record_evidence_outcome",
        "Record whether a previously logged claim turned out to be true or false once that's known "
        "(e.g. the user corrected you, or confirmed you were right). Updates source reliability scores.",
        {
            "entry_id": {"type": "string"},
            "outcome": {"type": "string", "description": "confirmed_true | confirmed_false | partially_true"},
            "note": {"type": "string"},
        },
        ["entry_id", "outcome"],
    ),
    _tool(
        "why_did_you_believe",
        "Look up the most recent logged claim-check matching this text, with its full evidence trail - "
        "use this when the user asks why you said/believed something.",
        {"claim": {"type": "string", "description": "The claim text (or a fragment of it) to search for"}},
        ["claim"],
    ),
    _tool(
        "get_source_reliability",
        "Get the running reliability score for an evidence source, based on how often claims citing it "
        "turned out to be correct.",
        {"source": {"type": "string"}},
        ["source"],
    ),
    _tool(
        "get_recent_evidence_entries",
        "List the most recently logged claim-checks.",
        {"limit": {"type": "integer", "description": "Default 20"}},
    ),
    _tool(
        "get_untrustworthy_sources",
        "List evidence sources whose reliability score has dropped below a safe threshold, based on "
        "enough judged history to be meaningful - worth being cautious about citing further.",
    ),
    # --- Failure Pattern Learning Engine ------------------------------------
    _tool(
        "check_tool_failure_risk",
        "Check the empirical failure risk for a tool before calling it, based on its recent real "
        "failure history and whether some other tool has reliably preceded its failures.",
        {"tool_name": {"type": "string"}},
        ["tool_name"],
    ),
    _tool(
        "get_failure_patterns",
        "List learned failure patterns (recurring error signatures) for a tool, or across all tools "
        "if no tool_name is given, ranked by risk (frequency + recency).",
        {"tool_name": {"type": "string"}, "limit": {"type": "integer", "description": "Default 20"}},
    ),
    _tool(
        "get_failure_pattern_report",
        "Get a full report of the top failure patterns and tool-chain precursor pairs (tools that "
        "reliably precede another tool's failures) learned so far.",
        {"limit": {"type": "integer", "description": "Default 15"}},
    ),
]
