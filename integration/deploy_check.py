"""
Final deployment readiness check (Phase 29.4/29.5)
======================================================
Combines every other Phase 29 module into one GO / NO-GO answer, the
same way core/startup.py combines its checks into one printed report -
except this one is meant to be run *before* shipping a build, not on
every boot:

    1. runs core.startup.run_startup_checks()   (subsystems up?)
    2. runs pipeline_test.run_pipeline_test()    (do they connect?)
    3. runs perf_optimizer.run_perf_optimizer()  (fast enough?)
    4. reads error_hardening's current circuit status (anything open?)

GO requires: no startup FAILs that aren't already-known-optional
(internet being offline is a WARN, not a blocker - see
core/startup.py's own docstring), the pipeline test passing, and no
stage averaging above the perf threshold. A single NO-GO reason is
enough to fail the whole check; every reason found is still listed so
nothing has to be re-run to see the next problem.
"""

import platform
import sys
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from .pipeline_test import run_pipeline_test, PipelineReport
from .perf_optimizer import run_perf_optimizer, PerfReport
from .error_hardening import get_hardened_handler

# Startup checks whose failure is documented as non-fatal degradation
# in core/startup.py's own docstrings, so a NO-GO shouldn't hinge on
# them alone.
NON_BLOCKING_STARTUP_CHECKS = {"internet"}


@dataclass
class DeployReport:
    go: bool
    reasons: List[str] = field(default_factory=list)
    startup: Dict = field(default_factory=dict)
    pipeline: Optional[PipelineReport] = None
    perf: Optional[PerfReport] = None
    circuits: Dict = field(default_factory=dict)
    generated_at: float = field(default_factory=time.time)
    python_version: str = field(default_factory=lambda: platform.python_version())

    def summary(self) -> str:
        lines = [
            "=" * 60,
            f"[phase29] DEPLOYMENT READINESS - {'GO' if self.go else 'NO-GO'}",
            f"  python={self.python_version}  generated={time.ctime(self.generated_at)}",
            "=" * 60,
            "",
            "-- startup checks --",
        ]
        for name, (ok, detail) in self.startup.items():
            blocking = "" if (ok or name in NON_BLOCKING_STARTUP_CHECKS) else " (BLOCKING)"
            lines.append(f"  [{'OK' if ok else 'WARN'}] {name}: {detail}{blocking}")

        if self.pipeline is not None:
            lines.append("")
            lines.append(self.pipeline.summary())
        if self.perf is not None:
            lines.append("")
            lines.append(self.perf.summary())
        if self.circuits:
            lines.append("")
            lines.append("-- error hardening circuits --")
            for ctx, s in self.circuits.items():
                lines.append(f"  {ctx}: {s}")

        lines.append("")
        if self.reasons:
            lines.append("NO-GO reasons:")
            for r in self.reasons:
                lines.append(f"  - {r}")
        else:
            lines.append("No blocking issues found.")
        return "\n".join(lines)


def run_deploy_check(perf_runs: int = 3) -> DeployReport:
    reasons: List[str] = []

    try:
        from core.startup import run_startup_checks

        startup = run_startup_checks(verbose=False)
    except Exception as e:
        startup = {}
        reasons.append(f"could not run core.startup checks: {e}")

    for name, (ok, detail) in startup.items():
        if not ok and name not in NON_BLOCKING_STARTUP_CHECKS:
            reasons.append(f"startup check '{name}' failed: {detail}")

    pipeline = run_pipeline_test()
    if not pipeline.ok:
        failed = [s.name for s in pipeline.stages if not s.ok]
        reasons.append(f"pipeline test failed at stage(s): {', '.join(failed)}")

    perf = run_perf_optimizer(runs=perf_runs, persist=True)
    if perf.slow_stages:
        reasons.append(f"stage(s) averaging above {perf.threshold_ms:.0f}ms: {', '.join(perf.slow_stages)}")

    circuits = get_hardened_handler().status()
    open_circuits = [ctx for ctx, s in circuits.items() if s["state"] == "open"]
    if open_circuits:
        reasons.append(f"circuit(s) currently open: {', '.join(open_circuits)}")

    return DeployReport(
        go=not reasons,
        reasons=reasons,
        startup=startup,
        pipeline=pipeline,
        perf=perf,
        circuits=circuits,
    )


if __name__ == "__main__":
    report = run_deploy_check()
    print(report.summary())
    sys.exit(0 if report.go else 1)
