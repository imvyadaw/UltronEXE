"""Command runner
===============
Run raw shell commands (with a destructive-command blocklist).
"""

import subprocess
from pathlib import Path
from typing import Dict


class CommandRunner:
    """Runs raw shell commands. Blocks a short list of obviously destructive ones."""

    def __init__(self):
        self.current_dir = Path.home()

    def run_command(self, command: str = "", timeout: int = 30) -> Dict:
        """Execute a command via cmd.exe."""
        if not command:
            return {"error": "No command provided"}
        dangerous = [
            "format c:",
            "format /",
            "rd /s /q c:\\",
            "rmdir /s /q c:\\",
            "del /f /s /q c:\\",
            "del /q c:\\*",
            ":(){:|:&};:",
            "shutdown /s",
            "shutdown -s",
        ]
        command_lower = command.lower()
        for d in dangerous:
            if d in command_lower:
                return {"error": "Dangerous command blocked"}

        try:
            result = subprocess.run(
                command, shell=True, capture_output=True, text=True, timeout=timeout, cwd=str(self.current_dir)
            )
            return {
                "stdout": result.stdout[:3000] if result.stdout else "",
                "stderr": result.stderr[:500] if result.stderr else "",
                "success": result.returncode == 0,
            }

        except subprocess.TimeoutExpired:
            return {"error": "Command timed out"}
        except Exception as e:
            return {"error": str(e)}
