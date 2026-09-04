"""
MULTI_AGENT_SWARM
====================
    agent_orchestrator.py   - the one entry point: handle_request() splits
                               a request across specialists,
                               run_swarm_review() sends one question to
                               several at once and combines their answers
    specialist_agents/      - code/research/writer/devops/data_analyst/
                               security, each wrapping an existing agents/
                               or skills/ module (or, for writer_agent.py,
                               a new focused-Groq-prompt capability)
    agent_communication.py  - per-agent inbox + broadcast message bus
    task_delegation.py      - decompose(request) -> subtasks,
                               assign(subtasks, agents) -> who does what
    consensus_engine.py     - combine several agents' answers to the same
                               question into one (majority/unanimous/weighted)
    swarm_memory.py         - SQLite blackboard: task log, key/value
                               scratch space, message history

Import order: swarm_memory.py has no dependency on anything else here;
agent_communication.py depends on it (message logging);
specialist_agents/* depend only on base_specialist.py plus whichever
one existing agents/skills module each wraps; task_delegation.py and
consensus_engine.py depend on nothing here (pure functions over
plain dicts); agent_orchestrator.py depends on all of the above plus
PHASE_17_1_FOUNDATION's phase16_bridge.

Nothing in memory/, core/, ai/, agents/, skills/, main.py,
PHASE_17_1_FOUNDATION/, PHASE_17_2_COGNITIVE_BRAIN/, or
PHASE_17_3_MEMORY_SYSTEM/ imports anything from here - purely
additive, same guarantee every prior Phase 17 package makes.
"""

from multi_agent_swarm.agent_orchestrator import get_orchestrator, AgentSwarmOrchestrator
from multi_agent_swarm.agent_communication import get_agent_bus, AgentBus
from multi_agent_swarm.task_delegation import get_task_delegator, TaskDelegator
from multi_agent_swarm.consensus_engine import get_consensus_engine, ConsensusEngine
from multi_agent_swarm.swarm_memory import get_swarm_memory, SwarmMemory

__all__ = [
    "get_orchestrator",
    "AgentSwarmOrchestrator",
    "get_agent_bus",
    "AgentBus",
    "get_task_delegator",
    "TaskDelegator",
    "get_consensus_engine",
    "ConsensusEngine",
    "get_swarm_memory",
    "SwarmMemory",
]
