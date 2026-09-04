"""Specialist-agent tool registry (coder only)
================================================
Wires agents/coder.py's CoderAgent into the AI tool-calling loop. This is
the only agents/*.py module that adds genuinely new capability - the rest
(browser_agent, vision_agent, windows_agent, memory_agent, automation_agent)
are thin wrappers around subsystems already exposed as tools elsewhere
(browser control, app open/close, memory, automation/macro), and were
deliberately left out of the tool schema here to avoid handing the model
two differently-named tools for the same underlying action. They're still
reachable directly via core/assistant.py's `specialist_agents` dict
(ULTRON_SPECIALIST_AGENTS_ENABLED) for any non-tool-call use.

Pattern mirrors ai/system_config_tools.py: lazy singleton + a flat
AGENT_TOOLS / AGENT_DIRECT_HANDLERS pair, merged at the bottom of
ai/tools_schema.py and ai/tool_runtime.py respectively.
"""

from typing import Dict


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


AGENT_TOOLS = [
    _tool(
        "coder_generate",
        "Write code for a described task. Does NOT execute the code - review it (or call "
        "coder_review) before running anything it returns.",
        {
            "task": {"type": "string", "description": "What the code should do"},
            "language": {"type": "string", "description": "Target language (default python)"},
        },
        ["task"],
    ),
    _tool(
        "coder_review",
        "Review a piece of code for bugs/issues before it gets executed or shown as final.",
        {
            "code": {"type": "string", "description": "The code to review"},
            "language": {"type": "string", "description": "Language of the code (default python)"},
        },
        ["code"],
    ),
    _tool(
        "coder_explain",
        "Explain what a piece of code does in plain language.",
        {
            "code": {"type": "string", "description": "The code to explain"},
        },
        ["code"],
    ),
]


_instances: Dict[str, object] = {}


def _get_coder():
    if "coder" not in _instances:
        from agents.coder import get_coder

        _instances["coder"] = get_coder()
    return _instances["coder"]


def _pick(d: dict, keys: list) -> dict:
    return {k: d[k] for k in keys if k in d and d[k] is not None}


def _h_generate(args: dict) -> Dict:
    return _get_coder().generate(**_pick(args, ["task", "language"]))


def _h_review(args: dict) -> Dict:
    return _get_coder().review(**_pick(args, ["code", "language"]))


def _h_explain(args: dict) -> Dict:
    return _get_coder().explain(**_pick(args, ["code"]))


AGENT_DIRECT_HANDLERS = {
    "coder_generate": _h_generate,
    "coder_review": _h_review,
    "coder_explain": _h_explain,
}
