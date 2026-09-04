"""
Windows Terminal / cmd automation
====================================
Runs commands via subprocess (captured output) or opens a visible
terminal window pre-positioned in a folder for interactive work.
"""

from typing import Dict

from apps.base_app import BaseApp


class TerminalApp(BaseApp):
    """Run shell commands and open terminal windows in a given folder."""

    APP_NAME = "terminal"
    PROCESS_NAMES = ["windowsterminal.exe", "cmd.exe", "conhost.exe"]
    EXE_HINTS = ["wt", "wt.exe", "cmd.exe"]

    def run_command(self, args) -> Dict:  # noqa: D401 - override for str convenience
        """Accepts either a list of args or a single shell command string."""
        if isinstance(args, str):
            import subprocess

            try:
                subprocess.Popen(args, shell=True)
                return {"success": True, "command": args}
            except Exception as e:
                return {"error": str(e)}
        return super().run_command(args)

    def run_and_capture_command(self, command: str, timeout: float = 30.0) -> Dict:
        """Run a shell command and wait for its output."""
        import subprocess

        try:
            result = subprocess.run(command, shell=True, capture_output=True, text=True, timeout=timeout)
            return {
                "success": result.returncode == 0,
                "returncode": result.returncode,
                "stdout": result.stdout.strip(),
                "stderr": result.stderr.strip(),
            }
        except subprocess.TimeoutExpired:
            return {"error": f"Command timed out after {timeout}s"}
        except Exception as e:
            return {"error": str(e)}

    def open_here(self, path: str) -> Dict:
        """Open a visible terminal window with its working directory set to path.

        SECURITY FIX (found during audit): this used to build
        f'start cmd /K cd /d "{path}"' and run it via shell=True - a
        path containing a `"` or a shell metacharacter (`&`, `|`, `%`,
        backtick, etc.) would break out of the quoting and inject
        arbitrary commands into the same shell. `path` isn't always
        user-typed, but it can come from anywhere a caller resolves a
        folder from (voice transcription, a filename found on disk,
        another tool's output), so it can't be trusted to be
        injection-safe. Fixed by launching cmd.exe directly with `cwd`
        set natively (no shell, no string interpolation) instead of
        building a shell command string at all.
        """
        exe = self.resolve_executable()
        try:
            if exe and "wt" in exe.lower():
                return self.run_command([exe, "-d", path])
            import subprocess

            subprocess.Popen(
                ["cmd.exe"],
                cwd=path,
                shell=False,
                creationflags=subprocess.CREATE_NEW_CONSOLE,
            )
            return {"success": True, "path": path}
        except Exception as e:
            return {"error": str(e)}
