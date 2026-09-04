"""
Performance optimization (Phase 29.2)
========================================
core/perf_trace.py answers "how long did *this* voice turn take, stage
by stage" - single turn, in-memory only, by design (see its docstring).
That's the right tool mid-turn, but it can't answer "is stage X
*reliably* slow, or was that one run just unlucky", because nothing
keeps a history across turns.

This module runs pipeline_test.run_pipeline_test() N times back to
back, keeps every stage's elapsed_ms across all N runs, and reports
mean/p50/p95/max per stage plus which stages cross a configurable
threshold - the same kind of percentile view perf_trace.py deliberately
doesn't keep, built on top of it rather than duplicating its
single-turn tracer.

Also persists each run's summary into the existing
database/intelligence/performance_metrics.db (via
database.get_database_manager()) when available, so perf history
survives past this process - reusing Phase 20.6/28's database layer
instead of inventing a second one.
"""

import statistics
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from .pipeline_test import run_pipeline_test, PipelineReport

# Anything slower than this on average is flagged for tuning. Tuned to
# "clearly worth looking at", not a hard SLA - stages like
# intelligence_core touch several bridges and are expected to run
# slower than a single sqlite round trip.
DEFAULT_THRESHOLD_MS = 250.0


@dataclass
class StageStats:
    name: str
    samples: List[float]

    @property
    def mean(self) -> float:
        return statistics.fmean(self.samples) if self.samples else 0.0

    @property
    def p50(self) -> float:
        return statistics.median(self.samples) if self.samples else 0.0

    @property
    def p95(self) -> float:
        if not self.samples:
            return 0.0
        ordered = sorted(self.samples)
        idx = min(len(ordered) - 1, int(round(0.95 * (len(ordered) - 1))))
        return ordered[idx]

    @property
    def max(self) -> float:
        return max(self.samples) if self.samples else 0.0


@dataclass
class PerfReport:
    runs: int
    stage_stats: Dict[str, StageStats] = field(default_factory=dict)
    threshold_ms: float = DEFAULT_THRESHOLD_MS
    failures: int = 0

    @property
    def slow_stages(self) -> List[str]:
        return [name for name, s in self.stage_stats.items() if s.mean > self.threshold_ms]

    def summary(self) -> str:
        lines = [f"[phase29] perf optimizer - {self.runs} run(s), threshold={self.threshold_ms:.0f}ms"]
        for name, s in self.stage_stats.items():
            flag = " <-- SLOW" if s.mean > self.threshold_ms else ""
            lines.append(
                f"  {name}: mean={s.mean:.1f}ms p50={s.p50:.1f}ms " f"p95={s.p95:.1f}ms max={s.max:.1f}ms{flag}"
            )
        if self.failures:
            lines.append(f"  ({self.failures} of {self.runs} run(s) had at least one failing stage)")
        if self.slow_stages:
            lines.append("  recommendations:")
            for name in self.slow_stages:
                lines.append(f"    - {name}: {_recommendation(name)}")
        else:
            lines.append("  no stage exceeded the threshold.")
        return "\n".join(lines)


def _recommendation(stage_name: str) -> str:
    # Static, hand-written per known stage rather than generic advice -
    # each of these maps to a real, applicable lever in this codebase.
    return {
        "intent_router": "cache compiled regex patterns / classify() results for repeated utterances.",
        "intelligence_core": "check intelligence.adaptive_performance's routing tier - a probe utterance "
        "hitting a cloud model tier will always dominate; confirm it's using the local/simple tier.",
        "goal_manager": "check core/goal_manager.py's storage backend isn't doing a full-table scan on create_goal().",
        "executor": "confirm the tool registry lookup in core/executor.py is a dict lookup, not a linear scan.",
        "database_roundtrip": "reuse the DatabaseManager's thread-local connection instead of reconnecting; "
        "check database/intelligence/*.db has the expected indexes.",
    }.get(stage_name, "profile this stage directly - no codebase-specific recommendation on file for it.")


def _persist(report: PerfReport) -> Optional[str]:
    try:
        from database import get_database_manager

        dbm = get_database_manager()
        if dbm is None:
            return None
        dbm.execute(
            "performance_metrics.db",
            "CREATE TABLE IF NOT EXISTS phase29_perf_runs "
            "(ts REAL, runs INTEGER, stage TEXT, mean_ms REAL, p95_ms REAL, slow INTEGER)",
        )
        now = time.time()
        for name, s in report.stage_stats.items():
            dbm.execute(
                "performance_metrics.db",
                "INSERT INTO phase29_perf_runs (ts, runs, stage, mean_ms, p95_ms, slow) " "VALUES (?, ?, ?, ?, ?, ?)",
                (now, report.runs, name, s.mean, s.p95, int(s.mean > report.threshold_ms)),
            )
        return "performance_metrics.db:phase29_perf_runs"
    except Exception:
        # Persistence is a bonus, not a requirement - an unavailable/locked
        # DB shouldn't stop perf reporting itself.
        return None


def run_perf_optimizer(
    runs: int = 5,
    threshold_ms: float = DEFAULT_THRESHOLD_MS,
    persist: bool = True,
) -> PerfReport:
    stage_samples: Dict[str, List[float]] = {}
    failures = 0
    for _ in range(max(1, runs)):
        r: PipelineReport = run_pipeline_test()
        if not r.ok:
            failures += 1
        for stage in r.stages:
            stage_samples.setdefault(stage.name, []).append(stage.elapsed_ms)

    report = PerfReport(
        runs=runs,
        stage_stats={name: StageStats(name, samples) for name, samples in stage_samples.items()},
        threshold_ms=threshold_ms,
        failures=failures,
    )
    if persist:
        _persist(report)
    return report


if __name__ == "__main__":
    print(run_perf_optimizer().summary())
