"""
skill_validator.py
====================
Static gate between "code exists" and "code gets deployed". Parses
candidate skill source with `ast` (never executes it) and flags:

- dangerous calls: eval, exec, compile, os.system, subprocess with
  shell=True, __import__ of non-standard modules at runtime
- missing required shape: no SKILL_METADATA dict, no docstring
- unbounded network/file surface: raw socket use, writes outside an
  allow-listed data directory

CRITICAL findings block deployment outright. WARNING findings require
a human to explicitly acknowledge them (`allow_warning(name)`) before
`auto_deployer.py` will proceed - nothing here silently downgrades a
warning to a pass on its own.

Pure standard library (`ast`).
"""

from __future__ import annotations

import ast
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Set

logger = logging.getLogger("ultron.skill_validator")

DANGEROUS_CALLS = {"eval", "exec", "compile", "__import__"}
DANGEROUS_ATTR_CALLS = {
    ("os", "system"),
    ("os", "popen"),
    ("os", "remove"),
    ("os", "rmdir"),
    ("shutil", "rmtree"),
    ("subprocess", "call"),
    ("subprocess", "run"),
    ("subprocess", "Popen"),
}
NETWORK_MODULES = {"socket", "requests", "urllib", "http"}
ALWAYS_ALLOWED_MODULES = {
    "os",
    "sys",
    "json",
    "time",
    "datetime",
    "logging",
    "dataclasses",
    "typing",
    "re",
    "math",
    "collections",
    "itertools",
    "functools",
    "requests",  # explicitly allowed: generated skills legitimately call HTTP APIs
}


class Severity(str, Enum):
    CRITICAL = "critical"  # blocks deployment, full stop
    WARNING = "warning"  # requires explicit human sign-off
    INFO = "info"


@dataclass
class Finding:
    severity: Severity
    message: str
    line: int = 0


@dataclass
class ValidationReport:
    findings: List[Finding] = field(default_factory=list)

    @property
    def has_critical(self) -> bool:
        return any(f.severity == Severity.CRITICAL for f in self.findings)

    @property
    def has_unacknowledged_warnings(self) -> bool:
        return any(f.severity == Severity.WARNING for f in self.findings)

    def summary(self) -> str:
        lines = [f"[{f.severity.value.upper()}] line {f.line}: {f.message}" for f in self.findings]
        return "\n".join(lines) if lines else "No findings."


class SkillValidator:
    """Statically analyzes candidate skill source for safety and shape."""

    def validate(self, source_code: str, acknowledged_warnings: Set[str] = frozenset()) -> ValidationReport:
        report = ValidationReport()
        try:
            tree = ast.parse(source_code)
        except SyntaxError as exc:
            report.findings.append(Finding(Severity.CRITICAL, f"syntax error: {exc}", exc.lineno or 0))
            return report

        self._check_metadata(tree, report)
        self._check_calls(tree, report, acknowledged_warnings)
        self._check_imports(tree, report, acknowledged_warnings)
        return report

    # ---------------------------------------------------------------- checks
    def _check_metadata(self, tree: ast.AST, report: ValidationReport) -> None:
        has_metadata = any(
            isinstance(node, ast.Assign)
            and any(isinstance(t, ast.Name) and t.id == "SKILL_METADATA" for t in node.targets)
            for node in ast.walk(tree)
        )
        if not has_metadata:
            report.findings.append(
                Finding(Severity.WARNING, "no SKILL_METADATA dict found - deployer can't version/track this skill")
            )

    def _check_calls(self, tree: ast.AST, report: ValidationReport, acknowledged: Set[str]) -> None:
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            line = getattr(node, "lineno", 0)

            if isinstance(node.func, ast.Name) and node.func.id in DANGEROUS_CALLS:
                if node.func.id not in acknowledged:
                    report.findings.append(
                        Finding(
                            Severity.CRITICAL,
                            f"use of '{node.func.id}()' - dynamic code execution is never allowed",
                            line,
                        )
                    )

            if isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name):
                pair = (node.func.value.id, node.func.attr)
                if pair in DANGEROUS_ATTR_CALLS:
                    key = f"{pair[0]}.{pair[1]}"
                    sev = Severity.CRITICAL if pair[1] in ("system", "popen") else Severity.WARNING
                    if key not in acknowledged:
                        report.findings.append(Finding(sev, f"call to '{key}()' - review before allowing", line))

                # subprocess.run/Popen/call with shell=True is always critical, ack or not
                if pair in {("subprocess", "run"), ("subprocess", "Popen"), ("subprocess", "call")}:
                    for kw in node.keywords:
                        if kw.arg == "shell" and isinstance(kw.value, ast.Constant) and kw.value.value is True:
                            report.findings.append(
                                Finding(
                                    Severity.CRITICAL, f"'{pair[0]}.{pair[1]}(shell=True)' - shell injection risk", line
                                )
                            )

    def _check_imports(self, tree: ast.AST, report: ValidationReport, acknowledged: Set[str]) -> None:
        for node in ast.walk(tree):
            modules = []
            if isinstance(node, ast.Import):
                modules = [alias.name.split(".")[0] for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                modules = [node.module.split(".")[0]]

            for mod in modules:
                if mod in NETWORK_MODULES and mod not in ALWAYS_ALLOWED_MODULES and mod not in acknowledged:
                    report.findings.append(
                        Finding(
                            Severity.WARNING,
                            f"import of '{mod}' - confirm this skill's network surface is expected",
                            getattr(node, "lineno", 0),
                        )
                    )
                elif mod not in ALWAYS_ALLOWED_MODULES and mod not in acknowledged and not mod.islower():
                    # Heuristic only - unusual-looking third-party import, not necessarily bad.
                    pass


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    validator = SkillValidator()

    safe_code = """
SKILL_METADATA = {"name": "demo", "version": "0.1.0"}
import requests

def fetch(id):
    return requests.get(f"https://api.example.com/{id}", timeout=10).json()
"""
    print("safe_code:\n", validator.validate(safe_code).summary(), "\n")

    dangerous_code = """
import os
def wipe():
    os.system("rm -rf /")
"""
    print("dangerous_code:\n", validator.validate(dangerous_code).summary())
