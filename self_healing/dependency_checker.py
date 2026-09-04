"""
dependency_checker.py
========================
Verifies that ULTRON's required Python packages are installed (and,
optionally, meet a minimum version), and reports what's missing with
the exact `pip install` command to fix it. Also supports simple
"is this callable importable / does this executable exist on PATH"
checks for non-pip dependencies (e.g. ffmpeg, a local Ollama binary).

This module only *reports* - it never silently pip-installs things
on your behalf. Install commands are handed back as strings for you
(or auto_recovery.py, with your own explicit opt-in) to run.

Dependencies: none beyond the standard library (uses importlib.metadata).
"""

from __future__ import annotations

import logging
import shutil
from dataclasses import dataclass
from importlib import metadata as importlib_metadata
from importlib.util import find_spec
from typing import List, Optional

logger = logging.getLogger("ultron.dependency_checker")


@dataclass
class DependencyStatus:
    name: str
    kind: str  # "package" | "executable"
    found: bool
    installed_version: Optional[str] = None
    required_version: Optional[str] = None
    version_ok: bool = True
    fix_command: Optional[str] = None


def _parse_version(v: str) -> tuple:
    parts = []
    for chunk in v.split("."):
        digits = "".join(c for c in chunk if c.isdigit())
        parts.append(int(digits) if digits else 0)
    return tuple(parts)


class DependencyChecker:
    """Checks Python packages and PATH executables against what ULTRON expects."""

    def check_package(self, package_name: str, min_version: Optional[str] = None) -> DependencyStatus:
        spec_found = find_spec(package_name.replace("-", "_")) is not None
        installed_version = None
        if spec_found:
            try:
                installed_version = importlib_metadata.version(package_name)
            except importlib_metadata.PackageNotFoundError:
                from core.error_trace import log_swallowed as _lsw

                _lsw("self_healing.dependency_checker.check_package")

        version_ok = True
        if min_version and installed_version:
            version_ok = _parse_version(installed_version) >= _parse_version(min_version)

        found = spec_found
        fix_cmd = None
        if not found:
            fix_cmd = f"pip install {package_name}" + (f">={min_version}" if min_version else "")
        elif not version_ok:
            fix_cmd = f"pip install --upgrade {package_name}" + (f">={min_version}" if min_version else "")

        status = DependencyStatus(
            name=package_name,
            kind="package",
            found=found,
            installed_version=installed_version,
            required_version=min_version,
            version_ok=version_ok,
            fix_command=fix_cmd,
        )
        if not found or not version_ok:
            logger.warning("Dependency issue: %s", status)
        return status

    def check_executable(self, exe_name: str, install_hint: Optional[str] = None) -> DependencyStatus:
        found = shutil.which(exe_name) is not None
        status = DependencyStatus(
            name=exe_name, kind="executable", found=found, fix_command=None if found else install_hint
        )
        if not found:
            logger.warning("Missing executable on PATH: %s", exe_name)
        return status

    def check_all(self, packages: List[tuple], executables: Optional[List[tuple]] = None) -> List[DependencyStatus]:
        """
        packages: list of (name, min_version_or_None)
        executables: list of (name, install_hint_or_None)
        """
        results = [self.check_package(name, ver) for name, ver in packages]
        for name, hint in executables or []:
            results.append(self.check_executable(name, hint))
        return results

    def summarize(self, statuses: List[DependencyStatus]) -> str:
        problems = [s for s in statuses if not s.found or not s.version_ok]
        if not problems:
            return f"All {len(statuses)} dependencies OK."
        lines = [f"{len(problems)} of {len(statuses)} dependencies need attention:"]
        for s in problems:
            lines.append(f"  - {s.name}: " + (s.fix_command or "not found on PATH, no install hint provided"))
        return "\n".join(lines)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    checker = DependencyChecker()
    results = checker.check_all(
        packages=[("psutil", None), ("watchdog", None), ("totally_not_a_real_package", None)],
        executables=[("git", None)],
    )
    print(checker.summarize(results))
