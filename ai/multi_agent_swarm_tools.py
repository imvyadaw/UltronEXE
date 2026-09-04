r"""
Multi-agent swarm tool wiring
================================
multi_agent_swarm/ (agent_orchestrator, task_delegation, consensus_engine,
swarm_memory, agent_communication, specialist_agents/*) is a real,
fully-implemented package - not a stub, not a rename of anything in MJ.
It was genuinely built for Ultron: six specialist agents (code, research,
writer, devops, data_analyst, security) that can run in parallel on
independent subtasks, or all weigh in on the same question with a
consensus vote at the end.

The gap: core/assistant.py only ever instantiates it as
self.multi_agent_swarm (gated behind ULTRON_MULTI_AGENT_SWARM_ENABLED,
default off) for internal/manual use, and
voice_intelligence/full_duplex_engine.py only reaches it through a
narrow keyword heuristic ("then"/"and also"/"at the same time"/
"meanwhile") in voice mode. Neither ai/tools_schema.py nor
ai/tool_runtime.py had an entry for it, so the model itself could never
call get_orchestrator().handle_request()/.run_swarm_review() as a tool
- same "Unknown tool" class of gap as every prior JARVIS/Ultron audit
(self_management_tools.py, agents_tools.py, scenarios_tools.py, etc.),
just never caught for this package specifically.

Exposed here as three tools, always present in the schema (read-only /
delegates-to-already-permissioned specialists, same "always offer, no
extra gate at the schema level" reasoning as ai/offline_kb_tools.py):

    swarm_delegate_task   - split a multi-part request across the best-
                             matching specialists, run independent parts
                             in parallel, return one combined summary.
    swarm_review          - send the *same* question/content to several
                             (or all) specialists and combine their
                             answers via consensus_engine.py.
    swarm_recent_tasks    - read-only visibility into what the swarm has
                             done recently (swarm_memory.py's task log),
                             for "what did the swarm just do" questions.

Independent of the ULTRON_MULTI_AGENT_SWARM_ENABLED flag on purpose:
that flag only controls whether core/assistant.py keeps a *manual*
handle on the orchestrator for its own internal use; get_orchestrator()
itself is a plain module-level singleton with no gate of its own
(same relationship as e.g. intelligence/ultron_advanced/autonomous_learning.py
vs ai/autonomous_learning_tools.py above it in tools_schema.py) - so the
tool works the same whether or not that flag is set.
"""

from typing import Dict, List, Optional


def _tool(name: str, description: str, properties: dict = None, required: list = None) -> dict:
    """Identical shape to ai/tools_schema.py's _tool() - duplicated on
    purpose (see ai/scenarios_tools.py's docstring for why: avoids a
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


def _get_orchestrator():
    from multi_agent_swarm.agent_orchestrator import get_orchestrator

    return get_orchestrator()


def _get_swarm_memory():
    from multi_agent_swarm.swarm_memory import get_swarm_memory

    return get_swarm_memory()


_VALID_AGENTS = ["code", "research", "writer", "devops", "data_analyst", "security"]
_VALID_STRATEGIES = ["majority", "unanimous", "weighted"]


def _swarm_delegate_task(args: Dict) -> Dict:
    request = args.get("request", "")
    if not request or not request.strip():
        return {"error": "No request provided to delegate"}
    parallel = args.get("parallel", True)
    return _get_orchestrator().handle_request(request, parallel=bool(parallel))


def _swarm_review(args: Dict) -> Dict:
    question = args.get("question", "")
    if not question or not question.strip():
        return {"error": "No question provided for swarm review"}

    agent_names: Optional[List[str]] = args.get("agents") or None
    if agent_names:
        unknown = [a for a in agent_names if a not in _VALID_AGENTS]
        if unknown:
            return {"error": f"Unknown agent(s) {unknown} - choose from {_VALID_AGENTS}"}

    strategy = args.get("strategy", "majority")
    if strategy not in _VALID_STRATEGIES:
        return {"error": f"Unknown strategy '{strategy}' - choose from {_VALID_STRATEGIES}"}

    action = args.get("action", "review")
    return _get_orchestrator().run_swarm_review(question, agent_names=agent_names, strategy=strategy, action=action)


def _swarm_recent_tasks(args: Dict) -> Dict:
    limit = args.get("limit", 20)
    try:
        limit = max(1, min(int(limit), 100))
    except (TypeError, ValueError):
        limit = 20
    return _get_swarm_memory().recent_tasks(limit=limit)


SWARM_TOOLS = [
    _tool(
        "swarm_delegate_task",
        "Split a multi-part request across Ultron's specialist agent swarm "
        "(code, research, writer, devops, data_analyst, security) and run the "
        "independent parts in parallel, returning one combined result. Use "
        "this when a single request genuinely has several distinct sub-jobs "
        "(e.g. 'write a script AND research the API AND summarize the docs'), "
        "not for a single simple task - a plain request should still go "
        "straight to the normal single-purpose tool for it.",
        {
            "request": {
                "type": "string",
                "description": "The full multi-part request, in the user's own words.",
            },
            "parallel": {
                "type": "boolean",
                "description": "Run independent subtasks concurrently (default true). "
                "Set false only if the subtasks must run in a strict order.",
            },
        },
        ["request"],
    ),
    _tool(
        "swarm_review",
        "Send the SAME question or piece of content to several specialist "
        "agents at once (rather than splitting work across them) and combine "
        "their answers into one consensus verdict. Use for 'review this' / "
        "'is this safe' / 'sanity check this' style requests where more than "
        "one perspective (e.g. code_agent AND security_agent both weighing in "
        "on the same script) is more trustworthy than a single answer.",
        {
            "question": {
                "type": "string",
                "description": "The question or content every chosen specialist should independently weigh in on.",
            },
            "agents": {
                "type": "array",
                "items": {"type": "string", "enum": _VALID_AGENTS},
                "description": "Which specialists to ask. Omit to ask all six.",
            },
            "strategy": {
                "type": "string",
                "enum": _VALID_STRATEGIES,
                "description": "How to combine answers: 'majority' (most common vote wins), "
                "'unanimous' (only settles if every agent agrees, else flags dissent - use for "
                "safety/security sign-off), or 'weighted' (each agent's own confidence score picks the primary answer).",
            },
            "action": {
                "type": "string",
                "description": "What each specialist should do with the question, e.g. 'review' (default), 'assess', 'critique'.",
            },
        },
        ["question"],
    ),
    _tool(
        "swarm_recent_tasks",
        "See what Ultron's specialist agent swarm has worked on recently - "
        "which subtasks were dispatched, to which agent, and whether they "
        "completed or failed. Use for 'what did the swarm just do' / "
        "'did that finish' style follow-ups.",
        {
            "limit": {
                "type": "integer",
                "description": "Max number of recent tasks to return (default 20, max 100).",
            }
        },
    ),
]


SWARM_DIRECT_HANDLERS: Dict = {
    "swarm_delegate_task": _swarm_delegate_task,
    "swarm_review": _swarm_review,
    "swarm_recent_tasks": _swarm_recent_tasks,
}
