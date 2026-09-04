"""
Plugin sandbox
==============
Runs untrusted plugin code with reduced privileges instead of a bare
`exec()`/import, for the case where a marketplace-installed plugin's
register()/handler code shouldn't be trusted with full process access
by default. Two levels:

- run_snippet(): restricted in-process `exec` with a locked-down
  builtins dict, for small pieces of code (e.g. testing a plugin
  snippet before installing it). No file/network/process access.
- run_script(): out-of-process execution via subprocess with a
  wall-clock timeout, for a full plugin file - isolates crashes/hangs
  from the main Ultron process, though (unlike run_snippet) it does
  not restrict what the subprocess itself can import or do, since
  Python has no built-in OS-level sandbox; treat this as
  crash/hang-isolation, not a real security boundary.
"""

import builtins
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Dict

# Deliberately small: no `open`, `__import__`, `exec`, `eval`, `input`, etc.
_SAFE_NAMES = (
    "abs",
    "all",
    "any",
    "bool",
    "dict",
    "enumerate",
    "float",
    "int",
    "len",
    "list",
    "max",
    "min",
    "print",
    "range",
    "round",
    "set",
    "sorted",
    "str",
    "sum",
    "tuple",
    "zip",
)
_SAFE_BUILTINS = {name: getattr(builtins, name) for name in _SAFE_NAMES if hasattr(builtins, name)}


class PluginSandbox:
    """Restricted execution for plugin code snippets and scripts."""

    def run_snippet(self, code: str, timeout_seconds: float = 5.0) -> Dict:
        """Execute a short Python snippet with a locked-down builtins
        set and no access to the filesystem, network, or Ultron's own
        modules. Returns whatever the snippet assigned to `result`, if
        anything, plus captured print() output."""
        import io
        import contextlib
        import signal

        local_vars: Dict = {}
        stdout_capture = io.StringIO()

        def _timeout_handler(signum, frame):
            raise TimeoutError(f"Snippet exceeded {timeout_seconds}s")

        try:
            has_alarm = hasattr(signal, "SIGALRM")
            if has_alarm:
                signal.signal(signal.SIGALRM, _timeout_handler)
                signal.setitimer(signal.ITIMER_REAL, timeout_seconds)

            try:
                with contextlib.redirect_stdout(stdout_capture):
                    exec(code, {"__builtins__": _SAFE_BUILTINS}, local_vars)
            finally:
                if has_alarm:
                    signal.setitimer(signal.ITIMER_REAL, 0)

            return {
                "success": True,
                "result": local_vars.get("result"),
                "stdout": stdout_capture.getvalue(),
            }
        except TimeoutError as e:
            return {"error": str(e)}
        except Exception as e:
            return {"error": f"{type(e).__name__}: {e}", "stdout": stdout_capture.getvalue()}

    def run_script(self, script_path: str, timeout_seconds: float = 10.0, args: list = None) -> Dict:
        """Run a full Python script file in a subprocess, isolating hangs
        and crashes from the main Ultron process. Not a security
        boundary - only use with plugin code you already trust the
        provenance of."""
        path = Path(script_path)
        if not path.exists():
            return {"error": f"Script not found: {script_path}"}
        try:
            proc = subprocess.run(
                [sys.executable, str(path), *(args or [])],
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
            )
            return {
                "success": proc.returncode == 0,
                "return_code": proc.returncode,
                "stdout": proc.stdout,
                "stderr": proc.stderr,
            }
        except subprocess.TimeoutExpired:
            return {"error": f"Script exceeded {timeout_seconds}s timeout"}
        except Exception as e:
            return {"error": str(e)}

    def run_temp_snippet_as_script(self, code: str, timeout_seconds: float = 10.0) -> Dict:
        """Convenience: write a snippet to a temp file and run it via
        run_script(), for code that needs real imports/file access but
        should still be crash/hang-isolated from the main process."""
        try:
            with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False, encoding="utf-8") as f:
                f.write(code)
                temp_path = f.name
            result = self.run_script(temp_path, timeout_seconds)
            Path(temp_path).unlink(missing_ok=True)
            return result
        except Exception as e:
            return {"error": str(e)}
