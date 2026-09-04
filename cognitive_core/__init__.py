"""
COGNITIVE_CORE
==============
    context_bridge.py       - situational snapshot + memory + unified-bus
                               observability ("cognition:*" events)
    goal_planner.py          - goal -> sub-goals (wraps ai.planning.Planner
                               for the flat/quick path too)
    task_decomposer.py       - sub-goal -> workflow_engine-shaped tool steps
    self_critique_agent.py   - "was the goal actually achieved?" LLM check,
                               with a structural fallback if the LLM call fails
    autonomous_executor.py   - the bounded plan/execute/critique/replan loop
                               tying the four above together
    intent_resolver.py       - classifies open-ended requests as GOAL
                               (routes to autonomous_executor) vs everything
                               core.intent_router already owns

Import order: context_bridge has no dependency on the others; goal_planner
and task_decomposer only depend on ai.planning + ai.ai_router;
self_critique_agent only depends on ai.ai_router; autonomous_executor
depends on all four; intent_resolver depends on autonomous_executor
(imported lazily inside route(), to keep classify() import-light).

Nothing in Phase 16 (core/, ai/, agents/, main.py) imports anything from
here - same purely-additive guarantee as
PHASE_17_1_FOUNDATION/CORE_INTEGRATION.
"""

from cognitive_core.context_bridge import get_context_bridge
from cognitive_core.goal_planner import get_goal_planner
from cognitive_core.task_decomposer import get_task_decomposer
from cognitive_core.self_critique_agent import get_self_critique_agent
from cognitive_core.autonomous_executor import get_autonomous_executor

__all__ = [
    "get_context_bridge",
    "get_goal_planner",
    "get_task_decomposer",
    "get_self_critique_agent",
    "get_autonomous_executor",
]
