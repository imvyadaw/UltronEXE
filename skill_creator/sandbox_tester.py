"""
sandbox_tester.py
====================
Runs a candidate skill module's own self-test (or a harness you
supply) in a subprocess with a hard wall-clock timeout, a stripped
environment, a scratch working directory, and - where the platform
supports it (Linux/macOS via `resource`) - CPU time, memory, and
file-descriptor limits.

Honest limitation: this is process isolation, not a security
boundary against genuinely adversarial code - it does not sandbox
network access or provide the guarantees a container/VM would. It
exists to catch the ordinary failure modes of generated code
(infinite loops, runaway memory, crashes, obviously broken imports)
*before* `skill_validator.py` and a human look at it, not to safely
execute untrusted code from strangers. Never run anything through
this that you would not also be willing to read first.

Pure standard library.
"""

from __future__ import annotations

import logging
import os
import subprocess
import sys
import tempfile
import textwrap
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

logger = logging.getLogger("ultron.sandbox_tester")

DEFAULT_TIMEOUT_SECONDS = 10
DEFAULT_MEMORY_LIMIT_MB = 256

try:
    import resource

    _HAS_RESOURCE = True
except ImportError:
    _HAS_RESOURCE = False  # e.g. Windows


@dataclass
class SandboxResult:
    ok: bool
    stdout: str
    stderr: str
    return_code: Optional[int]
    timed_out: bool = False


def _limit_resources(memory_mb: int, cpu_seconds: int):
    """Returns a preexec_fn for subprocess.Popen, or None on platforms without `resource`."""
    if not _HAS_RESOURCE:
        return None

    def _apply():
        mem_bytes = memory_mb * 1024 * 1024
        resource.setrlimit(resource.RLIMIT_AS, (mem_bytes, mem_bytes))
        resource.setrlimit(resource.RLIMIT_CPU, (cpu_seconds, cpu_seconds))
        resource.setrlimit(resource.RLIMIT_NOFILE, (64, 64))
        # No core dumps left lying around from a crashing candidate.
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))

    return _apply


class SandboxTester:
    """Executes candidate skill source in an isolated subprocess."""

    def __init__(self, timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS, memory_limit_mb: int = DEFAULT_MEMORY_LIMIT_MB):
        self.timeout_seconds = timeout_seconds
        self.memory_limit_mb = memory_limit_mb

    def run(self, source_code: str, test_snippet: Optional[str] = None) -> SandboxResult:
        """Write `source_code` to a scratch module and execute it (plus an
        optional `test_snippet` appended after import) in a subprocess."""
        with tempfile.TemporaryDirectory(prefix="ultron_skill_sandbox_") as tmp:
            module_path = Path(tmp) / "candidate_skill.py"
            module_path.write_text(source_code)

            runner = textwrap.dedent(f"""
                import sys
                sys.path.insert(0, {str(tmp)!r})
                import candidate_skill  # noqa: F401
                {test_snippet or "print('module imported OK')"}
            """)
            runner_path = Path(tmp) / "_runner.py"
            runner_path.write_text(runner)

            env = {"PATH": os.environ.get("PATH", ""), "PYTHONDONTWRITEBYTECODE": "1"}

            try:
                proc = subprocess.run(
                    [sys.executable, str(runner_path)],
                    cwd=tmp,
                    env=env,
                    capture_output=True,
                    text=True,
                    timeout=self.timeout_seconds,
                    preexec_fn=(
                        _limit_resources(self.memory_limit_mb, self.timeout_seconds + 1) if _HAS_RESOURCE else None
                    ),
                )
            except subprocess.TimeoutExpired as exc:
                logger.warning("Sandbox run timed out after %ss", self.timeout_seconds)
                return SandboxResult(
                    ok=False, stdout=exc.stdout or "", stderr=exc.stderr or "", return_code=None, timed_out=True
                )

            ok = proc.returncode == 0
            if not ok:
                logger.warning("Sandbox run exited %s", proc.returncode)
            return SandboxResult(ok=ok, stdout=proc.stdout, stderr=proc.stderr, return_code=proc.returncode)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    tester = SandboxTester(timeout_seconds=5)

    good_code = "def add(a, b):\n    return a + b\n"
    print(tester.run(good_code, test_snippet="print(candidate_skill.add(2, 3))"))

    infinite_loop_code = "while True:\n    pass\n"
    print(tester.run(infinite_loop_code))
