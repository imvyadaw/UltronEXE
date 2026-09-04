"""Skill-executor tool registry
================================
Wires skills/skill_executor.py's SkillExecutor into the AI tool-calling
loop. This was the real gap found in the audit: core/assistant.py only
ever used skills.ai.commands.CommandProcessor, so any BaseSkill subclass
written for skill_executor.py's dispatch path (17 of them under skills/)
was unreachable from a live conversation even though the dispatch layer
itself worked fine standalone. This module is the fix - two tools,
skill_run and skill_list_available, give the model a way to discover and
invoke those skills the same way it calls everything else.

Pattern mirrors ai/system_config_tools.py: lazy singleton + a flat
SKILL_EXECUTOR_TOOLS / SKILL_EXECUTOR_DIRECT_HANDLERS pair, merged at the
bottom of ai/tools_schema.py and ai/tool_runtime.py respectively.
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


SKILL_EXECUTOR_TOOLS = [
    _tool(
        "skill_list_available",
        "List every skill registered with the skill-executor dispatch layer (name + "
        "description). Call this first if unsure what skill_run can do.",
    ),
    _tool(
        "skill_run",
        "Run a named skill's action through the skill-executor dispatch layer. Call "
        "skill_list_available first if the exact skill_name/action isn't already known.",
        {
            "skill_name": {"type": "string", "description": "The skill's registered name"},
            "action": {"type": "string", "description": "The action to invoke on that skill"},
            "kwargs": {"type": "object", "description": "Extra keyword arguments the action needs"},
        },
        ["skill_name", "action"],
    ),
]


def _h_list_available(args: dict) -> Dict:
    from skills.skill_executor import get_skill_executor

    return get_skill_executor().list_available()


def _h_run(args: dict) -> Dict:
    from skills.skill_executor import get_skill_executor

    kwargs = args.get("kwargs") or {}
    return get_skill_executor().run(args["skill_name"], args["action"], **kwargs)


SKILL_EXECUTOR_DIRECT_HANDLERS = {
    "skill_list_available": _h_list_available,
    "skill_run": _h_run,
}
