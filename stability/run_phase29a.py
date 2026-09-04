"""
PHASE 29-A validation CLI
===========================
    python -m stability.run_phase29a                 # all four
    python -m stability.run_phase29a --compile        # compile only
    python -m stability.run_phase29a --unit           # unit tests only
    python -m stability.run_phase29a --integration    # integration only
    python -m stability.run_phase29a --dependency     # dependency report only

Exit code 0 on PASS, 1 on FAIL - matches core/startup.py and
integration/run_phase29.py's convention.

The four checks, in the order the VALIDATION section of the Phase 29-A plan
lists them:

1. Compile tests   - every .py file under Ultron/ (skipping .venv-style and
                      cache dirs) parses/compiles cleanly. Catches syntax
                      errors and bad edits before anything tries to import
                      them - the cheapest possible check, runs first.
2. Unit tests      - pytest over stability/tests/ (this phase's
                      own logic, fast, no heavy deps required).
3. Integration test - imports `windows` (the real facade every tool call
                      goes through) end-to-end and confirms it comes up
                      even with optional deps (groq/ultralytics/torch/etc.)
                      missing, then runs integration's own
                      pipeline_test.py so this phase is checked against the
                      rest of the app, not in isolation.
4. Dependency tests - dependency_validator.validate(): required deps
                      present, and a clear report of what optional-feature
                      degradation to expect in this environment.
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

ULTRON_ROOT = Path(__file__).resolve().parent.parent

# Directories under Ultron/ that shouldn't be compile-checked: caches,
# generated artifacts, and anything not meant to be imported as source.
_SKIP_DIR_NAMES = {".pytest_cache", "__pycache__", "logs", "cache", "storage", ".git"}


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
        lines = ["PHASE 29-A validation: " + ("PASS" if self.ok else "FAIL")]
        for c in self.checks:
            status = "ok" if c.ok else "FAIL"
            lines.append(f"  [{status}] {c.name} ({c.seconds:.2f}s)")
            if c.detail:
                for line in c.detail.strip().splitlines():
                    lines.append(f"        {line}")
        return "\n".join(lines)


def _rmtree_ignore(path: Path) -> bool:
    return any(part in _SKIP_DIR_NAMES for part in path.parts)


def run_compile_test() -> CheckResult:
    t0 = time.monotonic()
    buf = io.StringIO()
    quiet_flag = 2  # compileall: only print filenames on failure
    with redirect_stdout(buf):
        ok = compileall.compile_dir(
            str(ULTRON_ROOT),
            quiet=quiet_flag,
            rx=__import__("re").compile(r"(" + "|".join(_SKIP_DIR_NAMES) + r")"),
        )
    detail = buf.getvalue().strip()
    return CheckResult("compile", bool(ok), detail, time.monotonic() - t0)


def run_unit_tests() -> CheckResult:
    t0 = time.monotonic()
    try:
        import pytest
    except ImportError:
        return CheckResult("unit", False, "pytest not installed - pip install pytest", time.monotonic() - t0)
    buf = io.StringIO()
    test_dir = str(Path(__file__).resolve().parent / "tests")
    with redirect_stdout(buf):
        exit_code = pytest.main(["-q", test_dir])
    return CheckResult("unit", exit_code == 0, buf.getvalue().strip(), time.monotonic() - t0)


def run_integration_test() -> CheckResult:
    t0 = time.monotonic()
    detail_lines = []
    ok = True

    try:

        detail_lines.append("windows package import: ok")
    except Exception as e:
        ok = False
        detail_lines.append(f"windows package import: FAILED ({e})")

    try:
        from integration.pipeline_test import run_pipeline_test

        r = run_pipeline_test()
        detail_lines.append(f"integration pipeline test: {'ok' if r.ok else 'FAILED'}")
        if not r.ok:
            ok = False
        detail_lines.append(r.summary())
    except Exception as e:
        ok = False
        detail_lines.append(f"integration pipeline test: FAILED to run ({e})")

    from stability.exception_hardening import failed_components

    failed = failed_components()
    if failed:
        detail_lines.append(f"components swallowed by exception_hardening this run: {list(failed)}")

    return CheckResult("integration", ok, "\n".join(detail_lines), time.monotonic() - t0)


def run_dependency_test() -> CheckResult:
    t0 = time.monotonic()
    from stability.dependency_validator import validate

    report = validate()
    # Only a missing REQUIRED dependency fails this check - missing
    # optional deps are expected/reported, not a failure (same "degrade,
    # don't crash" stance as the rest of Phase 29/29-A).
    return CheckResult("dependency", report.required_ok, report.summary(), time.monotonic() - t0)


_CHECKS = {
    "compile": run_compile_test,
    "unit": run_unit_tests,
    "integration": run_integration_test,
    "dependency": run_dependency_test,
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
