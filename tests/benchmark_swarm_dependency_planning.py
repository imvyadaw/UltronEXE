"""
Benchmark: multi_agent_swarm's OLD flat dispatch (task_delegation.py's
offline split, no dependency edges, no context passing) vs the NEW
dependency-aware DAG dispatch (dependency_planner.py + agent_orchestrator.py's
_dispatch_dag/_inject_dependency_context).

Demonstrates the concrete, confirmed bug this upgrade fixes: the swarm's
own README usage example -

    "Research the top 3 Python web frameworks, then write a short
     summary comparing them"

- splits into two independent subtasks under the old offline split, which
  agent_orchestrator.handle_request() then dispatches IN PARALLEL by
  default. specialist_agents/writer_agent.py's _run() reads
  task["description"] as the content to write about, which after the
  split is just "write a short summary comparing them" - the writer
  agent has no path to research_agent's actual findings.

No live LLM/API key in this sandbox (`groq` isn't even installed here),
so this benchmark:
  - exercises DependencyAwarePlanner.plan() against a stub router
    (same technique as tests/benchmark_deliberative_reasoning.py)
  - exercises AgentSwarmOrchestrator._dispatch_dag() /
    _inject_dependency_context() directly, with _dispatch() monkeypatched
    to a stub specialist so no real agent (and no groq import) is needed

This is a mechanism test, not a claim about real-world LLM decomposition
quality - run against a real ai_router on your own machine for that.

Usage:
    python -m tests.benchmark_swarm_dependency_planning
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from multi_agent_swarm.agent_orchestrator import AgentSwarmOrchestrator
from multi_agent_swarm.dependency_planner import DependencyAwarePlanner
from multi_agent_swarm.task_delegation import get_task_delegator

RESEARCH_FINDING = (
    "Top 3 Python web frameworks by usage: Django (batteries-included, ORM, "
    "admin panel), Flask (minimal, flexible, large ecosystem), FastAPI "
    "(async-first, type-hint-driven, built-in OpenAPI docs)."
)

REQUEST = "Research the top 3 Python web frameworks, then write a short summary comparing them"


class StubPlannerRouter:
    """Deterministic stand-in for ai_router, used only by DependencyAwarePlanner."""

    def complete(self, prompt: str, temperature: float = 0.2, max_tokens: int = 500) -> str:
        return (
            '[{"description": "Research the top 3 Python web frameworks", '
            '"type": "research", "depends_on": []}, '
            '{"description": "Write a short summary comparing them", '
            '"type": "writer", "depends_on": [0]}]'
        )


def stub_dispatch(agent_name: str, task: dict) -> dict:
    """Stands in for AgentSwarmOrchestrator._dispatch() - simulates exactly
    what specialist_agents/research_agent.py and writer_agent.py would do,
    without needing groq installed or network access."""
    description = task.get("description", "")
    if agent_name == "research":
        return {"result": RESEARCH_FINDING, "agent": "research"}
    if agent_name == "writer":
        if "Context from prior steps:" in description:
            # writer_agent._run() sees the actual research finding folded
            # into its description - can ground its summary in real content
            return {"result": f"Summary grounded in findings: {RESEARCH_FINDING[:60]}...", "agent": "writer"}
        # old behavior: writer_agent._run() only ever sees "write a short
        # summary comparing them" - "them" refers to nothing it has access
        # to, so it can only hallucinate or punt
        return {"result": "Summary of [UNSPECIFIED - no subject was provided in this task]", "agent": "writer"}
    return {"error": f"no stub for agent {agent_name}"}


def run_old_flat_dispatch() -> dict:
    """OLD behavior: task_delegation.py's offline split (no depends_on),
    dispatched in parallel with no dependency awareness or context passing -
    exactly what handle_request(use_dependency_planning=False) still does."""
    delegator = get_task_delegator()
    subtasks = delegator.decompose(REQUEST)
    for t in subtasks:
        t["depends_on"] = []
        # crude assignment mirroring assign()'s keyword scoring for this
        # specific pair of subtasks, without needing real agent instances
        t["agent"] = "research" if t["type"] == "research" else ("writer" if t["type"] == "writer" else None)

    results = []
    for t in subtasks:
        agent = t.get("agent")
        result = stub_dispatch(agent, t) if agent else {"error": "no specialist matched"}
        results.append({**t, "result": result})
    return {"request": REQUEST, "subtasks": results}


def run_new_dependency_aware_dispatch() -> dict:
    """NEW behavior: DependencyAwarePlanner + AgentSwarmOrchestrator's
    real _dispatch_dag()/_inject_dependency_context(), with only
    _dispatch() (the one call that would need a real specialist/groq)
    replaced by the stub above."""
    orchestrator = AgentSwarmOrchestrator()
    orchestrator._dispatch = stub_dispatch  # bypass real agent instantiation
    orchestrator._dep_planner = DependencyAwarePlanner(router_factory=lambda: StubPlannerRouter())

    subtasks = orchestrator._dep_planner.plan(REQUEST)
    assigned = [
        {**t, "agent": "research" if t["type"] == "research" else ("writer" if t["type"] == "writer" else None)}
        for t in subtasks
    ]
    results = orchestrator._dispatch_dag(assigned, parallel=True)
    return {"request": REQUEST, "subtasks": results}


def grounded(summary_text: str) -> bool:
    return "Django" in summary_text or "Flask" in summary_text or "FastAPI" in summary_text


def main():
    print("=" * 70)
    print("SWARM DEPENDENCY-AWARE DISPATCH BENCHMARK (stubbed, synthetic)")
    print("=" * 70)
    print(f"Request: {REQUEST!r}\n")

    old = run_old_flat_dispatch()
    new = run_new_dependency_aware_dispatch()

    old_writer = next(s["result"]["result"] for s in old["subtasks"] if s.get("agent") == "writer")
    new_writer = next(s["result"]["result"] for s in new["subtasks"] if s.get("agent") == "writer")

    print("OLD (flat, no dependency awareness):")
    print(f"  research subtask depends_on: {[s['depends_on'] for s in old['subtasks'] if s['agent']=='research']}")
    print(f"  writer output: {old_writer}")
    print(f"  writer summary actually grounded in research findings? {grounded(old_writer)}")
    print()
    print("NEW (dependency-aware DAG dispatch):")
    print(f"  writer subtask depends_on: {[s['depends_on'] for s in new['subtasks'] if s['agent']=='writer']}")
    print(f"  writer output: {new_writer}")
    print(f"  writer summary actually grounded in research findings? {grounded(new_writer)}")
    print()
    print("=" * 70)
    print(f"Result: OLD grounded={grounded(old_writer)}  NEW grounded={grounded(new_writer)}")
    print("=" * 70)


if __name__ == "__main__":
    main()
