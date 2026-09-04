"""Batch script manager
=======================
Same idea as powershell_manager.py's PowerShellScriptManager, but for
Windows batch files (.bat/.cmd) instead of PowerShell. windows/cmd/
runner.py's CommandRunner already runs a raw shell command string once,
ad hoc, via cmd.exe - it has no concept of a saved, named, reusable
script file either. This module adds that library layer: save a batch
script under a name, list/view/delete saved scripts, and run one by
name (via `cmd /c <path> <args>`, going through the same
subprocess.run() call shape and destructive-command blocklist idea
CommandRunner uses). Saved scripts live under
storage/cache/batch_scripts/<name>.bat.

Saving/viewing/listing is inert and not confirm-gated. Running or
deleting a saved script is confirm-gated - a saved .bat is arbitrary,
replayable code execution, arguably more consequential than a one-off
command since it can be run repeatedly or wired into a scheduled task
(see backup_scheduler.py / system_control/process/task_scheduler.py).
"""

import subprocess
from pathlib import Path
from typing import Dict

SCRIPTS_DIR = Path(__file__).resolve().parents[2] / "storage" / "cache" / "batch_scripts"

# Same philosophy as windows/cmd/runner.py's CommandRunner - block the
# obviously destructive ones even inside a saved script.
DANGEROUS_PATTERNS = [
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


class BatchScriptManager:
    """Save, list, run, and delete named .bat/.cmd scripts."""

    def __init__(self):
        SCRIPTS_DIR.mkdir(parents=True, exist_ok=True)
        self.current_dir = Path.home()

    def _safe_name(self, name: str) -> str:
        return "".join(c for c in name if c.isalnum() or c in ("_", "-"))[:100]

    def _path_for(self, name: str) -> Path:
        return SCRIPTS_DIR / f"{self._safe_name(name)}.bat"

    def save_script(self, name: str, content: str) -> Dict:
        """Save (or overwrite) a named batch script."""
        if not name or not content:
            return {"error": "name and content must both be non-empty"}
        safe = self._safe_name(name)
        if not safe:
            return {"error": "name must contain at least one alphanumeric character"}
        content_lower = content.lower()
        for pattern in DANGEROUS_PATTERNS:
            if pattern in content_lower:
                return {"error": "Refusing to save a script containing a blocked destructive command"}
        path = self._path_for(safe)
        overwrote = path.exists()
        try:
            path.write_text(content, encoding="utf-8")
            return {"success": True, "name": safe, "path": str(path), "overwrote": overwrote}
        except Exception as e:
            return {"error": str(e)}

    def list_scripts(self) -> Dict:
        """List all saved batch scripts."""
        try:
            names = sorted(p.stem for p in SCRIPTS_DIR.glob("*.bat"))
            return {"success": True, "scripts": names, "count": len(names)}
        except Exception as e:
            return {"error": str(e)}

    def get_script(self, name: str) -> Dict:
        """View a saved batch script's content."""
        path = self._path_for(name)
        if not path.exists():
            return {"error": f"No saved batch script named '{name}'"}
        try:
            return {"success": True, "name": path.stem, "content": path.read_text(encoding="utf-8")}
        except Exception as e:
            return {"error": str(e)}

    def delete_script(self, name: str, confirm: bool = False) -> Dict:
        """Delete a saved batch script. Confirm-gated."""
        path = self._path_for(name)
        if not path.exists():
            return {"error": f"No saved batch script named '{name}'"}
        if not confirm:
            return {
                "success": False,
                "needs_confirmation": True,
                "preview": f"Would delete saved batch script '{path.stem}'",
                "message": "Call again with confirm=true to apply.",
            }
        try:
            path.unlink()
            return {"success": True, "name": path.stem, "deleted": True}
        except Exception as e:
            return {"error": str(e)}

    def run_script(self, name: str, arguments: str = "", timeout: int = 60, confirm: bool = False) -> Dict:
        """Run a saved batch script by name (`cmd /c <path> <args>`).
        Confirm-gated - executes whatever the script contains."""
        path = self._path_for(name)
        if not path.exists():
            return {"error": f"No saved batch script named '{name}'"}
        if not confirm:
            preview = path.read_text(encoding="utf-8")[:200]
            return {
                "success": False,
                "needs_confirmation": True,
                "preview": f"Would run '{path.stem}' {arguments}:\n{preview}",
                "message": "Call again with confirm=true to apply.",
            }
        try:
            cmd = ["cmd", "/c", str(path)] + (arguments.split() if arguments else [])
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=str(self.current_dir),
            )
            return {
                "success": result.returncode == 0,
                "stdout": result.stdout[:3000] if result.stdout else "",
                "stderr": result.stderr[:500] if result.stderr else "",
            }
        except subprocess.TimeoutExpired:
            return {"error": "Batch script timed out"}
        except Exception as e:
            return {"error": str(e)}

    def run_adhoc(self, command: str, timeout: int = 30) -> Dict:
        """Run a one-off shell command without saving it first. Thin
        passthrough to windows/cmd/runner.py's CommandRunner, kept here
        so callers only need this one manager for every batch/cmd need."""
        from windows.cmd.runner import CommandRunner

        return CommandRunner().run_command(command, timeout=timeout)
