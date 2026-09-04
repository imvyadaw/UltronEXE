"""
Agent orchestrator
====================
The one entry point the rest of Ultron calls into MULTI_AGENT_SWARM
through - get_orchestrator().handle_request("...") for work that
should be split across specialists, or .run_swarm_review("...") for a
question that should go to several specialists at once and come back
as one cross-checked answer. Everything else in this package
(task_delegation.py, agent_communication.py, consensus_engine.py,
swarm_memory.py, specialist_agents/*.py) is a piece this file wires
together; nothing outside MULTI_AGENT_SWARM needs to import those
directly.

Agents are imported lazily (same ai/multi_agent.py philosophy) so
importing this module never pulls in Groq, the web-research pipeline,
or any other optional dependency until a specialist is actually used.
Emits "swarm:request_started" / "swarm:request_completed" on
PHASE_17_1_FOUNDATION's unified event bus via phase16_bridge, the same
one-way relationship PHASE_17_2_COGNITIVE_BRAIN and PHASE_17_3's
memory_consolidator.py already have with it - nothing in Phase 16,
17.1, 17.2, or 17.3 imports anything from here.
"""

from concurrent.futures import ThreadPoolExecutor
from typing import Dict, List, Optional

from core_integration.phase16_bridge import get_bridge
from multi_agent_swarm.agent_communication import get_agent_bus
from multi_agent_swarm.consensus_engine import get_consensus_engine
from multi_agent_swarm.swarm_memory import get_swarm_memory
from multi_agent_swarm.task_delegation import get_task_delegator

try:
    from core.logger import get_logger

    logger = get_logger("ultron.agent_orchestrator")
except Exception:  # pragma: no cover
    import logging

    logger = logging.getLogger("ultron.agent_orchestrator")
    if not logger.handlers:
        logging.basicConfig(level=logging.INFO)

try:
    from multi_agent_swarm.dependency_planner import get_dependency_planner
except Exception as exc:  # pragma: no cover
    get_dependency_planner = None

try:
    from cognitive_core.self_critique_agent import get_self_critique_agent
except Exception as exc:  # pragma: no cover
    get_self_critique_agent = None

# agent name -> (module path, class name), mirroring ai/multi_agent.py's
# _AGENT_PATHS exactly so the two orchestrators stay easy to compare.
_AGENT_PATHS = {
    "code": ("multi_agent_swarm.specialist_agents.code_agent", "SwarmCodeAgent"),
    "research": ("multi_agent_swarm.specialist_agents.research_agent", "SwarmResearchAgent"),
    "writer": ("multi_agent_swarm.specialist_agents.writer_agent", "SwarmWriterAgent"),
    "devops": ("multi_agent_swarm.specialist_agents.devops_agent", "SwarmDevOpsAgent"),
    "data_analyst": ("multi_agent_swarm.specialist_agents.data_analyst_agent", "SwarmDataAnalystAgent"),
    "security": ("multi_agent_swarm.specialist_agents.security_agent", "SwarmSecurityAgent"),
}

#: Hard cap on how many subtasks/agents one call fans out to at once -
#: same bounded-work philosophy as memory_consolidator.py's
#: MAX_ITEMS_PER_CYCLE, just for concurrency instead of a backlog.
MAX_PARALLEL_AGENTS = 6

#: Per-subtask retry budget when self-critique judges a result didn't
#: actually satisfy the subtask - same bounded-retry philosophy as
#: cognitive_core/autonomous_executor.py's MAX_SUBGOAL_ATTEMPTS.
MAX_SUBTASK_ATTEMPTS = 2

#: How much of a dependency's result text gets folded into a dependent
#: subtask's description - keeps prompts bounded even if an upstream
#: specialist returns something long (e.g. a big research dump).
MAX_CONTEXT_CHARS_PER_DEP = 1500


class AgentSwarmOrchestrator:
    """Coordinates specialist_agents/* via delegation, comms, and consensus."""

    def __init__(self):
        self._instances: Dict[str, object] = {}
        self._bridge = get_bridge()
        self._bus = get_agent_bus()
        self._memory = get_swarm_memory()
        self._delegator = get_task_delegator()
        self._consensus = get_consensus_engine()
        try:
            self._dep_planner = get_dependency_planner() if get_dependency_planner else None
        except Exception as e:  # e.g. ai_router import chain failed at construction time
            logger.info(f"[agent_orchestrator] dependency planner unavailable, using offline split only: {e}")
            self._dep_planner = None
        self._critique = get_self_critique_agent() if get_self_critique_agent else None

    def get_agent(self, name: str):
        """Instantiate (once) and return the specialist for `name`."""
        if name not in _AGENT_PATHS:
            raise KeyError(f"Unknown specialist agent: {name}")
        if name not in self._instances:
            import importlib

            module_path, class_name = _AGENT_PATHS[name]
            module = importlib.import_module(module_path)
            agent = getattr(module, class_name)()
            self._bus.subscribe(name)
            self._instances[name] = agent
        return self._instances[name]

    def all_agents(self) -> Dict[str, object]:
        """Every specialist, instantiated. Used by task_delegation.assign()
        and run_swarm_review() when the caller doesn't name a subset."""
        return {name: self.get_agent(name) for name in _AGENT_PATHS}

    # -- split-and-delegate -----------------------------------------------
    def handle_request(self, request: str, parallel: bool = True, use_dependency_planning: bool = True) -> Dict:
        """Decompose `request` into subtasks, assign each to the
        best-matching specialist, and run them.

        use_dependency_planning=True (default) uses dependency_planner.py's
        LLM-based decomposition, which - unlike the plain offline split -
        knows when one subtask needs another's *result* (e.g. "research X,
        then summarize it") and runs the DAG accordingly: independent
        subtasks still run concurrently (parallel=True) via a bounded
        thread pool, but a dependent subtask waits for its dependencies
        and gets their actual output folded into its own description
        before it runs. Each dispatched subtask also gets one bounded
        self-critique + retry pass (mirrors cognitive_core/
        autonomous_executor.py's retry-on-failed-critique loop).

        use_dependency_planning=False keeps the exact old behavior:
        task_delegation.py's offline split, no dependency awareness, no
        critique/retry - for callers that already depend on that shape
        or want the zero-LLM-call fast path.
        """
        self._bridge.events.emit("swarm:request_started", request=request)

        if use_dependency_planning and self._dep_planner is not None:
            subtasks = self._dep_planner.plan(request)
        else:
            subtasks = self._delegator.decompose(request)

        if not subtasks:
            return {"error": "Empty request - nothing to delegate"}

        assigned = self._delegator.assign(subtasks, self.all_agents())
        results = self._dispatch_dag(assigned, parallel=parallel)

        completed = all("error" not in r["result"] for r in results if r["agent"])
        summary = {"request": request, "completed": completed, "subtasks": results}
        self._bridge.events.emit("swarm:request_completed", completed=completed, subtask_count=len(results))
        return summary

    def _dispatch_dag(self, assigned: List[Dict], parallel: bool) -> List[Dict]:
        """Runs `assigned` respecting each task's "depends_on" (list of
        earlier "order" values, empty for plain task_delegation.py output
        since that never sets it) in topological batches: every subtask
        whose dependencies are already done runs in one batch (concurrent
        if parallel=True and the batch has more than one), then the next
        batch, and so on. A subtask that names a dependency which never
        ran (bad index, upstream had no agent) just runs without that
        context rather than deadlocking the batch."""
        by_order = {t.get("order", i): t for i, t in enumerate(assigned)}
        done: Dict[int, Dict] = {}
        results: List[Dict] = []
        remaining = set(by_order.keys())

        while remaining:
            ready = [o for o in remaining if all(d in done for d in by_order[o].get("depends_on", []))]
            if not ready:
                # Should be structurally impossible (dependency_planner.py
                # rejects cycles before this point) - fail open rather than
                # hang: run everything left with whatever context exists.
                logger.info("[agent_orchestrator] no ready subtask in DAG dispatch - running remainder unordered")
                ready = list(remaining)

            batch = [self._inject_dependency_context(by_order[o], done) for o in ready]

            def run_one(task: Dict) -> Dict:
                agent_name = task.get("agent")
                if agent_name is None:
                    return {**task, "result": {"error": "No specialist matched this subtask"}}
                return {**task, "result": self._dispatch_with_retry(agent_name, task)}

            if parallel and len(batch) > 1:
                with ThreadPoolExecutor(max_workers=min(MAX_PARALLEL_AGENTS, len(batch))) as pool:
                    batch_results = list(pool.map(run_one, batch))
            else:
                batch_results = [run_one(t) for t in batch]

            for r in batch_results:
                order = r.get("order")
                done[order] = r["result"]
                results.append(r)
            remaining -= set(ready)

        results.sort(key=lambda r: r.get("order", 0))
        return results

    def _inject_dependency_context(self, task: Dict, done: Dict[int, Dict]) -> Dict:
        """Folds each completed dependency's result into `task`'s
        description - the one field every specialist_agents/*.py._run()
        already reads - so a dependent subtask sees what it actually
        depends on without any specialist needing to change."""
        deps = task.get("depends_on") or []
        if not deps:
            return task

        pieces = []
        for d in deps:
            dep_result = done.get(d)
            if not dep_result:
                continue
            text = dep_result.get("result") if isinstance(dep_result, dict) else None
            if not text:
                continue
            text = str(text)[:MAX_CONTEXT_CHARS_PER_DEP]
            pieces.append(text)

        if not pieces:
            return task

        context_block = "\n\n".join(pieces)
        new_task = dict(task)
        new_task["description"] = f"{task.get('description', '')}\n\nContext from prior steps:\n{context_block}"
        return new_task

    def _dispatch_with_retry(self, agent_name: str, task: Dict) -> Dict:
        """_dispatch() plus one bounded self-critique + retry pass -
        mirrors cognitive_core/autonomous_executor.py's
        _run_subgoal_with_retries(), applied to a single swarm subtask
        instead of a whole autonomous goal. Skipped entirely (falls
        straight through to a plain _dispatch()) if self_critique_agent
        isn't importable - additive, never a hard dependency."""
        result = self._dispatch(agent_name, task)
        if self._critique is None:
            return result

        current_task = task
        for attempt in range(1, MAX_SUBTASK_ATTEMPTS + 1):
            report = {"steps": [{"label": agent_name, "success": "error" not in result, **result}]}
            critique = self._critique.critique(current_task.get("description", ""), report)
            result["critique"] = critique
            if critique.get("satisfied", True) or attempt == MAX_SUBTASK_ATTEMPTS:
                break

            feedback = critique.get("suggested_fix") or critique.get("reason") or ""
            current_task = {
                **current_task,
                "description": f"{task.get('description', '')}\n\n(Previous attempt didn't fully address this: {feedback})",
            }
            result = self._dispatch(agent_name, current_task)

        return result

    def _dispatch(self, agent_name: str, task: Dict) -> Dict:
        """Run one subtask on one named agent, with swarm_memory logging
        and a bus broadcast either side of the call."""
        task_id = self._memory.record_task(
            task_type=task.get("type") or agent_name, description=task.get("description", ""), assigned_agent=agent_name
        ).get("task_id")

        self._bus.broadcast("orchestrator", {"event": "task_started", "agent": agent_name, "task_id": task_id})
        try:
            agent = self.get_agent(agent_name)
        except KeyError as e:
            return {"error": str(e)}

        result = agent.handle(task)
        status = "failed" if "error" in result else "completed"
        if task_id is not None:
            self._memory.update_task_status(task_id, status, result)
        self._bus.broadcast(
            "orchestrator", {"event": "task_finished", "agent": agent_name, "task_id": task_id, "status": status}
        )
        return result

    # -- swarm review / consensus ------------------------------------------
    def run_swarm_review(
        self, question: str, agent_names: Optional[List[str]] = None, strategy: str = "majority", action: str = "review"
    ) -> Dict:
        """Send the *same* question to several specialists at once (rather
        than splitting it into subtasks) and combine their answers via
        consensus_engine.py. Defaults to every specialist if `agent_names`
        isn't given - useful for something like "review this script",
        where code_agent.py and security_agent.py should each weigh in
        on the same input rather than dividing the work."""
        names = agent_names or list(_AGENT_PATHS.keys())
        task = {"type": "review", "description": question, "action": action}

        agent_results: Dict[str, Dict] = {}
        with ThreadPoolExecutor(max_workers=min(MAX_PARALLEL_AGENTS, len(names))) as pool:
            futures = {name: pool.submit(self._dispatch, name, task) for name in names}
            for name, future in futures.items():
                agent_results[name] = future.result()

        outcome = self._consensus.reach_consensus(agent_results, strategy=strategy)
        outcome["question"] = question
        return outcome


_orchestrator: Optional[AgentSwarmOrchestrator] = None


def get_orchestrator() -> AgentSwarmOrchestrator:
    """Process-wide singleton, same pattern as ai/multi_agent.py's own
    get_orchestrator() (different namespace - no collision)."""
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = AgentSwarmOrchestrator()
    return _orchestrator
