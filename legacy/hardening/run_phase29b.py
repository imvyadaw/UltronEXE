"""
PHASE 29-B validation CLI
===========================
    python -m hardening.run_phase29b                 # all three
    python -m hardening.run_phase29b --compile        # compile only
    python -m hardening.run_phase29b --unit           # unit tests only
    python -m hardening.run_phase29b --integration    # integration only

Exit code 0 on PASS, 1 on FAIL - same convention as core/startup.py,
integration/run_phase29.py, and stability/run_phase29a.py.

Three checks (no dependency check here - unlike 29-A, this phase adds no
new third-party dependency; it's pure-stdlib logic sitting on top of
things 29-A already validated the environment for):

1. Compile  - every .py file under this package parses cleanly.
2. Unit     - pytest over hardening/tests/ (fabricated
              tool_name/args/result triples, no real windows/browser/
              automation calls - see the tests module docstring).
3. Integration - imports this package for real and round-trips
              guard_turn() against a couple of fabricated turns (one
              clean success, one flagged failure), confirming the full
              Result Normalizer -> Evidence Collector -> Verification
              Engine -> Truth Gate -> Response Truth Guard chain actually
              wires together - not just that each piece's own unit tests
              pass in isolation.
"""

from __future__ import annotations

import compileall
import io
import sys
import time
from contextlib import redirect_stdout
from dataclasses import dataclass, field
from pathlib import Path
from typing import List

PACKAGE_ROOT = Path(__file__).resolve().parent


@dataclass
class CheckResult:
    name: str
    ok: bool
    detail: str = ""
    seconds: float = 0.0


@dataclass
class ValidationReport:
    checks: List[CheckResult] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return all(c.ok for c in self.checks)

    def summary(self) -> str:
        lines = ["PHASE 29-B validation: " + ("PASS" if self.ok else "FAIL")]
        for c in self.checks:
            status = "ok" if c.ok else "FAIL"
            lines.append(f"  [{status}] {c.name} ({c.seconds:.2f}s)")
            if c.detail:
                for line in c.detail.strip().splitlines():
                    lines.append(f"        {line}")
        return "\n".join(lines)


def run_compile_test() -> CheckResult:
    t0 = time.monotonic()
    buf = io.StringIO()
    with redirect_stdout(buf):
        ok = compileall.compile_dir(str(PACKAGE_ROOT), quiet=2)
    detail = buf.getvalue().strip()
    return CheckResult("compile", bool(ok), detail, time.monotonic() - t0)


def run_unit_tests() -> CheckResult:
    t0 = time.monotonic()
    try:
        import pytest
    except ImportError:
        return CheckResult("unit", False, "pytest not installed - pip install pytest", time.monotonic() - t0)
    buf = io.StringIO()
    test_dir = str(PACKAGE_ROOT / "tests")
    with redirect_stdout(buf):
        exit_code = pytest.main(["-q", test_dir])
    return CheckResult("unit", exit_code == 0, buf.getvalue().strip(), time.monotonic() - t0)


def run_integration_test() -> CheckResult:
    t0 = time.monotonic()
    detail_lines = []
    ok = True

    try:
        from hardening import guard_turn, ResultState

        clean = guard_turn(
            "I've opened Chrome for you, Sir.",
            tool_names=["open_application"],
            tool_args=[{"app_name": "Chrome"}],
            tool_results=[{"success": True, "app_name": "Chrome"}],
        )
        if not (clean.ok and clean.turn_state == ResultState.VERIFIED_SUCCESS):
            ok = False
            detail_lines.append(f"clean-success smoke turn did not verify as expected: {clean.summary()}")
        else:
            detail_lines.append("clean-success smoke turn: ok")

        flagged = guard_turn(
            "Done, Sir - all set.",
            tool_names=["send_email"],
            tool_args=[{"to": "boss@example.com"}],
            tool_results=[{"success": False, "error": "SMTP auth failed"}],
        )
        if flagged.ok or flagged.turn_state != ResultState.VERIFIED_FAILURE:
            ok = False
            detail_lines.append("unmentioned-failure smoke turn should have been flagged and wasn't")
        else:
            detail_lines.append("unmentioned-failure smoke turn: correctly flagged")
    except Exception as e:
        ok = False
        detail_lines.append(f"hardening import/smoke test: FAILED ({e})")

    return CheckResult("integration", ok, "\n".join(detail_lines), time.monotonic() - t0)


_CHECKS = {
    "compile": run_compile_test,
    "unit": run_unit_tests,
    "integration": run_integration_test,
}


def run_all() -> ValidationReport:
    report = ValidationReport()
    for name, fn in _CHECKS.items():
        report.checks.append(fn())
    return report


def main() -> int:
    args = sys.argv[1:]
    selected = [a.lstrip("-") for a in args if a.lstrip("-") in _CHECKS]

    if selected:
        report = ValidationReport(checks=[_CHECKS[name]() for name in selected])
    else:
        report = run_all()

    print(report.summary())
    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
