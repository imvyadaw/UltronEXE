"""tools/shell.py - raw shell command execution.

SECURITY NOTE (found during audit): this file previously ran any
string via subprocess.run(..., shell=True) with zero blocklist,
zero timeout error handling, and zero output size cap - unlike
every other shell-executing module in this codebase
(windows/cmd/runner.py, system_control/*), which all gate
destructive commands. It is not currently imported by the live
tool-calling path (ai/tools_schema.py + ai/tool_runtime.py) or by
tools/registry.py's discovery list, so it isn't reachable by the
LLM today - but an unguarded shell runner sitting in tools/ is a
landmine for whoever wires it up next without noticing. Hardened
here to match the safety bar the rest of the repo already uses.
"""

import subprocess
from typing import Dict, Optional

# Same class of destructive patterns windows/cmd/runner.py blocks -
# kept here too since this module doesn't import that one.
_DANGEROUS = (
    "format c:",
    "format /",
    "rd /s /q c:\\",
    "rmdir /s /q c:\\",
    "del /f /s /q c:\\",
    "del /q c:\\*",
    ":(){:|:&};:",
    "shutdown /s",
    "shutdown -s",
    "mkfs",
    "dd if=",
    "> /dev/sda",
)


class ShellTool:
    """Runs a raw shell command. Blocks an obviously-destructive
    short list and always caps output/time - it does not know the
    caller's intent, so it can't do full command-injection analysis,
    only stop the worst-case commands."""

    def run(self, command: str, cwd: Optional[str] = None, timeout: float = 30) -> Dict:
        if not command or not command.strip():
            return {"error": "No command provided"}
        command_lower = command.lower()
        for pattern in _DANGEROUS:
            if pattern in command_lower:
                return {"error": f"Blocked: command matches destructive pattern '{pattern}'"}
        try:
            result = subprocess.run(
                command,
                shell=True,
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            return {
                "success": result.returncode == 0,
                "returncode": result.returncode,
                "stdout": (result.stdout or "")[-10000:],
                "stderr": (result.stderr or "")[-10000:],
            }
        except subprocess.TimeoutExpired:
            return {"error": f"Command timed out after {timeout}s"}
        except FileNotFoundError as e:
            return {"error": f"Command not found: {e}"}
        except Exception as e:
            return {"error": str(e)}
