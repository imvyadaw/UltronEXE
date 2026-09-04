"""
specialist_agents
====================
Six focused agents, each a thin swarm-shaped wrapper around an
existing agents/ or skills/ module (or, for writer_agent.py, a new
capability built the same way agents/coding_agent.py already is):

    code_agent.py          - wraps agents/coding_agent.py
    security_agent.py      - wraps agents/security_agent.py
    research_agent.py      - wraps skills/web/research.py
    devops_agent.py         - wraps skills/windows/manager.py
    data_analyst_agent.py   - wraps skills/data/processor.py
    writer_agent.py         - new capability (focused Groq prompt,
                               same shape as agents/coding_agent.py)

All six subclass base_specialist.py's BaseSpecialistAgent, so
agent_orchestrator.py, task_delegation.py, and consensus_engine.py can
treat them identically: `.can_handle(task) -> float` for routing,
`.handle(task) -> Dict` for execution.

Import order: base_specialist.py has no dependency on anything else
here; the six agents each depend on it plus the one existing module
they wrap, not on each other.
"""

from multi_agent_swarm.specialist_agents.base_specialist import BaseSpecialistAgent
from multi_agent_swarm.specialist_agents.code_agent import SwarmCodeAgent
from multi_agent_swarm.specialist_agents.research_agent import SwarmResearchAgent
from multi_agent_swarm.specialist_agents.writer_agent import SwarmWriterAgent
from multi_agent_swarm.specialist_agents.devops_agent import SwarmDevOpsAgent
from multi_agent_swarm.specialist_agents.data_analyst_agent import SwarmDataAnalystAgent
from multi_agent_swarm.specialist_agents.security_agent import SwarmSecurityAgent

__all__ = [
    "BaseSpecialistAgent",
    "SwarmCodeAgent",
    "SwarmResearchAgent",
    "SwarmWriterAgent",
    "SwarmDevOpsAgent",
    "SwarmDataAnalystAgent",
    "SwarmSecurityAgent",
]
