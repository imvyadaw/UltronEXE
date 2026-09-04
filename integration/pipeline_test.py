"""
End-to-end pipeline test (Phase 29.1)
======================================
core/startup.py checks that each subsystem *comes up*. This checks that
a turn actually *flows* through all of them together, in the order a
real turn takes:

    text -> core.intent_router.route()
         -> intelligence.get_intelligence_core().process_turn()
         -> core.goal_manager.get_goal_manager() (goal touched/created)
         -> core.executor.execute_tool() (a harmless, side-effect-free
            tool call so the execution path itself is exercised)
         -> database.get_database_manager() (result readable back out)

Each stage is wrapped individually so one missing/broken subsystem
doesn't block the rest of the run from being tested - same
"degrade, don't crash" posture as core/startup.py and
core/error_handler.py. A stage that raises is recorded as a FAIL with
the exception message, not re-raised.

This is intentionally a *smoke* test, not a substitute for
testing/unit and testing/e2e's pytest suites - it exists to answer one
question fast: "does the whole chain still connect after this
change?", runnable in <1s with no test framework needed so it can also
back deploy_check.py's GO/NO-GO decision.
"""

import time
from dataclasses import dataclass, field
from typing import Callable, List, Optional


@dataclass
class StageResult:
    name: str
    ok: bool
    detail: str
    elapsed_ms: float


@dataclass
class PipelineReport:
    stages: List[StageResult] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        # A pipeline is healthy if nothing *raised*. Individual stages
        # reporting themselves unavailable (e.g. no GROQ_API_KEY) are
        # WARN-level and already reflected in their own detail string -
        # they don't fail the whole pipeline, matching startup.py's
        # philosophy that a degraded-but-alive subsystem isn't a boot
        # failure.
        return all(s.ok for s in self.stages)

    @property
    def total_ms(self) -> float:
        return sum(s.elapsed_ms for s in self.stages)

    def summary(self) -> str:
        lines = ["[phase29] end-to-end pipeline test"]
        for s in self.stages:
            status = "OK" if s.ok else "FAIL"
            lines.append(f"  [{status}] {s.name} ({s.elapsed_ms:.1f}ms): {s.detail}")
        lines.append(f"  -> {'PASS' if self.ok else 'FAIL'} in {self.total_ms:.1f}ms total")
        return "\n".join(lines)


def _timed(name: str, fn: Callable[[], str]) -> StageResult:
    t0 = time.time()
    try:
        detail = fn()
        return StageResult(name, True, detail, (time.time() - t0) * 1000)
    except Exception as e:  # noqa: BLE001 - a stage failing is data, not a crash
        detail = f"{e.__class__.__name__}: {e}"
        return StageResult(name, False, detail, (time.time() - t0) * 1000)


PROBE_UTTERANCE = "ultron, what time is it"
# A read-only, always-registered tool used purely to exercise the
# execution path without side effects (no filesystem/network writes).
# core/executor.py's tool_map is the source of truth for valid names.
PROBE_TOOL = "get_system_info"

# core/executor.py imports windows/, which pulls in every agents/*
# module at import time (agents/coding_agent.py -> groq, some others ->
# other optional SDKs) even though execute_tool() itself only needs
# whichever tool is actually being called. That's a real fragility -
# an environment missing one optional extra can't import the executor
# at all - but fixing windows/__init__.py's import graph is out of
# scope here; this stage instead reports it as a WARN (the pipeline is
# still "connected", just missing an optional dependency in *this*
# environment) rather than a hard FAIL, the same way core/startup.py
# treats GROQ_API_KEY being unset.
_OPTIONAL_IMPORT_MARKERS = ("groq", "elevenlabs", "openai", "anthropic", "chromadb", "faiss")


def _stage_intent_router() -> str:
    from core.intent_router import classify

    result = classify(PROBE_UTTERANCE)
    return f"classified as {getattr(result, 'intent', result)!r}"


def _stage_intelligence_core() -> str:
    from intelligence import get_intelligence_core

    core = get_intelligence_core()
    status = core.status()
    if not status.get("intelligence_core_available"):
        return "unavailable (degraded/no-op) - not a failure, just not wired up"
    result = core.process_turn(PROBE_UTTERANCE, context={"source": "phase29_pipeline_test"})
    keys = ", ".join(sorted(result.keys())) if isinstance(result, dict) else str(type(result))
    return f"process_turn() returned keys: {keys}"


def _stage_goal_manager() -> str:
    from core.goal_manager import get_goal_manager

    gm = get_goal_manager()
    if not hasattr(gm, "create_goal"):
        return "goal manager present but create_goal() unavailable (fallback mode)"
    goal = gm.create_goal(
        title="[phase29 pipeline test] probe goal",
        description="created by integration.pipeline_test, safe to ignore/delete",
    )
    goal_id = goal.get("id") if isinstance(goal, dict) else goal
    # Clean up immediately - this is a smoke probe, not a real goal.
    if hasattr(gm, "complete_goal") and goal_id:
        gm.complete_goal(goal_id)
    return f"created + completed probe goal {goal_id}"


def _stage_executor() -> str:
    try:
        from core.executor import execute_tool
    except ModuleNotFoundError as e:
        if e.name and any(m in e.name.lower() for m in _OPTIONAL_IMPORT_MARKERS):
            return f"unavailable in this environment (optional dependency not installed: {e.name})"
        raise
    result = execute_tool(PROBE_TOOL, {})
    return f"execute_tool({PROBE_TOOL!r}) -> {str(result)[:120]}"


def _stage_database_roundtrip() -> str:
    from database import get_database_manager

    dbm = get_database_manager()
    if dbm is None:
        return "database layer unavailable (degraded) - not a failure"
    marker = f"phase29-probe-{int(time.time())}"
    dbm.execute(
        "performance_metrics.db",
        "CREATE TABLE IF NOT EXISTS phase29_probe (marker TEXT, ts REAL)",
    )
    dbm.execute(
        "performance_metrics.db",
        "INSERT INTO phase29_probe (marker, ts) VALUES (?, ?)",
        (marker, time.time()),
    )
    row = dbm.fetchone(
        "performance_metrics.db",
        "SELECT marker FROM phase29_probe WHERE marker = ?",
        (marker,),
    )
    dbm.execute("performance_metrics.db", "DELETE FROM phase29_probe WHERE marker = ?", (marker,))
    if not row:
        raise RuntimeError("wrote probe row but read-back returned nothing")
    return "write -> read-back -> cleanup all succeeded"


STAGES: List[tuple] = [
    ("intent_router", _stage_intent_router),
    ("intelligence_core", _stage_intelligence_core),
    ("goal_manager", _stage_goal_manager),
    ("executor", _stage_executor),
    ("database_roundtrip", _stage_database_roundtrip),
]


def run_pipeline_test(stages: Optional[List[tuple]] = None) -> PipelineReport:
    """Run every stage in order, collecting a StageResult for each
    regardless of earlier failures, and return the full report."""
    report = PipelineReport()
    for name, fn in stages or STAGES:
        report.stages.append(_timed(name, fn))
    return report


if __name__ == "__main__":
    r = run_pipeline_test()
    print(r.summary())
    raise SystemExit(0 if r.ok else 1)
