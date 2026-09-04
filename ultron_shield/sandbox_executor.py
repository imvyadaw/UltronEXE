"""
sandbox_executor.py
====================
The one place in ULTRON that's allowed to run an external command on
your behalf - and only under a `Policy` you define ahead of time.
Distinct from SKILL_CREATOR's `sandbox_tester.py` (which trial-runs
*generated Python source* to catch bugs before deployment): this
module runs already-decided-on *external commands* (e.g. a
registered `remote_controller` action that needs to shell out to a
real CLI tool) under tight, explicit constraints.

A `Policy` is an allowlist, not a denylist: only executables named in
`allowed_executables` can run, only from `allowed_working_dirs`, with
a capped timeout and (where `resource` is available) capped memory/
CPU/file-descriptors. There is no `shell=True` anywhere in this
module - arguments are always passed as a list, never interpolated
into a shell string, so shell metacharacters in an argument can't do
anything unexpected.

Pure standard library.
"""

from __future__ import annotations

import logging
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger("ultron.sandbox_executor")

try:
    import resource

    _HAS_RESOURCE = True
except ImportError:
    _HAS_RESOURCE = False


@dataclass
class Policy:
    allowed_executables: List[str]  # e.g. ["/usr/bin/say", "/usr/bin/notify-send"]
    allowed_working_dirs: List[str]  # commands may only run cwd'd inside these
    timeout_seconds: float = 10.0
    memory_limit_mb: int = 256
    allow_network: bool = False  # informational flag consumers can check/enforce upstream


@dataclass
class ExecutionResult:
    ok: bool
    stdout: str
    stderr: str
    return_code: Optional[int]
    timed_out: bool = False
    rejected_reason: Optional[str] = None


def _limit_resources(memory_mb: int, cpu_seconds: int):
    if not _HAS_RESOURCE:
        return None

    def _apply():
        mem_bytes = memory_mb * 1024 * 1024
        resource.setrlimit(resource.RLIMIT_AS, (mem_bytes, mem_bytes))
        resource.setrlimit(resource.RLIMIT_CPU, (cpu_seconds, cpu_seconds))
        resource.setrlimit(resource.RLIMIT_NOFILE, (64, 64))
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))

    return _apply


class SandboxExecutor:
    """Runs allowlisted external commands under a Policy. Refuses anything
    not explicitly permitted rather than trying to detect what's dangerous."""

    def __init__(self, policy: Policy):
        self.policy = policy

    def run(
        self,
        executable: str,
        args: Optional[List[str]] = None,
        working_dir: Optional[str] = None,
        env: Optional[Dict[str, str]] = None,
    ) -> ExecutionResult:
        args = args or []

        resolved_exe = str(Path(executable).resolve())
        if resolved_exe not in [str(Path(e).resolve()) for e in self.policy.allowed_executables]:
            logger.warning("Rejected execution of non-allowlisted executable: %s", executable)
            return ExecutionResult(
                ok=False,
                stdout="",
                stderr="",
                return_code=None,
                rejected_reason=f"'{executable}' is not in allowed_executables",
            )

        cwd = working_dir or (self.policy.allowed_working_dirs[0] if self.policy.allowed_working_dirs else None)
        if cwd is not None:
            resolved_cwd = str(Path(cwd).resolve())
            allowed_dirs = [str(Path(d).resolve()) for d in self.policy.allowed_working_dirs]
            if not any(resolved_cwd == d or resolved_cwd.startswith(d + os.sep) for d in allowed_dirs):
                logger.warning("Rejected execution with disallowed working dir: %s", cwd)
                return ExecutionResult(
                    ok=False,
                    stdout="",
                    stderr="",
                    return_code=None,
                    rejected_reason=f"working dir '{cwd}' is outside allowed_working_dirs",
                )

        run_env = {"PATH": os.environ.get("PATH", "")}
        if env:
            run_env.update(env)

        try:
            proc = subprocess.run(
                [resolved_exe, *args],
                cwd=cwd,
                env=run_env,
                capture_output=True,
                text=True,
                timeout=self.policy.timeout_seconds,
                shell=False,  # never shell=True - args are always a list, never interpolated
                preexec_fn=(
                    _limit_resources(self.policy.memory_limit_mb, int(self.policy.timeout_seconds) + 1)
                    if _HAS_RESOURCE
                    else None
                ),
            )
        except subprocess.TimeoutExpired as exc:
            logger.warning("Sandboxed command timed out: %s", executable)
            return ExecutionResult(
                ok=False, stdout=exc.stdout or "", stderr=exc.stderr or "", return_code=None, timed_out=True
            )
        except OSError as exc:
            return ExecutionResult(
                ok=False, stdout="", stderr=str(exc), return_code=None, rejected_reason=f"failed to start: {exc}"
            )

        ok = proc.returncode == 0
        if not ok:
            logger.warning("Sandboxed command '%s' exited %s", executable, proc.returncode)
        return ExecutionResult(ok=ok, stdout=proc.stdout, stderr=proc.stderr, return_code=proc.returncode)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    policy = Policy(
        allowed_executables=["/bin/echo"],
        allowed_working_dirs=["/tmp"],
        timeout_seconds=5,
    )
    executor = SandboxExecutor(policy)

    print(executor.run("/bin/echo", ["hello from the sandbox"], working_dir="/tmp"))
    print(executor.run("/bin/rm", ["-rf", "/tmp/whatever"]))  # rejected: not allowlisted
