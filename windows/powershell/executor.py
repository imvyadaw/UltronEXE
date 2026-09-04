"""PowerShell executor
====================
Run PowerShell scripts/commands with output capture, separate from the
generic cmd.exe runner in windows/cmd/runner.py - useful for cmdlets
(Get-Process, Get-Service, etc.) that don't exist in plain cmd. Shares
the same destructive-command blocklist philosophy as CommandRunner.

Renamed from powershell/powershell.py (PowerShellRunner) as part of
Phase 8's windows/ restructure. Only windows/__init__.py imported the
old module, so this is a clean rename.
"""

import subprocess
from pathlib import Path
from typing import Dict

DANGEROUS_PATTERNS = [
    "remove-item c:\\",
    "format-volume",
    "clear-disk",
    "stop-computer",
    "restart-computer",
    "remove-item -recurse -force c:\\",
]


class PowerShellExecutor:
    """Runs PowerShell commands/scripts. Blocks a short list of obviously destructive ones."""

    def __init__(self):
        self.current_dir = Path.home()

    def run_powershell(self, script: str, timeout: int = 30) -> Dict:
        """Execute a PowerShell command or script string."""
        script_lower = script.lower()
        for pattern in DANGEROUS_PATTERNS:
            if pattern in script_lower:
                return {"error": "Dangerous PowerShell command blocked"}

        try:
            result = subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=str(self.current_dir),
            )
            return {
                "stdout": result.stdout[:3000] if result.stdout else "",
                "stderr": result.stderr[:500] if result.stderr else "",
                "success": result.returncode == 0,
            }
        except FileNotFoundError:
            return {"error": "PowerShell not found - this is only available on Windows"}
        except subprocess.TimeoutExpired:
            return {"error": "PowerShell command timed out"}
        except Exception as e:
            return {"error": str(e)}

    def run_script_file(self, script_path: str, timeout: int = 60) -> Dict:
        """Execute a .ps1 script file."""
        try:
            path = Path(script_path).expanduser().resolve()
            if not path.exists():
                return {"error": f"Script not found: {path}"}
            result = subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", str(path)],
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            return {
                "stdout": result.stdout[:3000] if result.stdout else "",
                "stderr": result.stderr[:500] if result.stderr else "",
                "success": result.returncode == 0,
            }
        except FileNotFoundError:
            return {"error": "PowerShell not found - this is only available on Windows"}
        except subprocess.TimeoutExpired:
            return {"error": "PowerShell script timed out"}
        except Exception as e:
            return {"error": str(e)}
