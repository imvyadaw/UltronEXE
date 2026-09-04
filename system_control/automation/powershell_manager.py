"""PowerShell script manager
============================
windows/powershell/executor.py's PowerShellExecutor already runs a raw
PowerShell command string or an arbitrary .ps1 file path, once, ad
hoc - it has no concept of a *named, saved* script. This module builds
that missing library layer on top of it: save a script under a name,
list/view/delete saved scripts, run one by name (writing it to a temp
.ps1 and delegating to PowerShellExecutor.run_script_file so the
execution path - and its dangerous-pattern blocklist - is exactly the
same one already used for ad-hoc scripts), and manage the effective
PowerShell execution policy. Saved scripts live under
storage/cache/powershell_scripts/<name>.ps1 so they survive a restart,
same convention as automation/macro/macro.py's MACROS_DIR and
automation/workflow/workflow.py's WORKFLOWS_DIR.

Saving/viewing/listing a script is inert (no execution), so those are
not confirm-gated. Running a saved script, deleting one, and changing
the execution policy are confirm-gated, same as every other
consequential action in this package.
"""

from pathlib import Path
from typing import Dict

from windows.powershell.executor import PowerShellExecutor

SCRIPTS_DIR = Path(__file__).resolve().parents[2] / "storage" / "cache" / "powershell_scripts"

VALID_POLICIES = ("Restricted", "AllSigned", "RemoteSigned", "Unrestricted", "Bypass", "Default", "Undefined")


class PowerShellScriptManager:
    """Save, list, run, and delete named PowerShell scripts; manage execution policy."""

    def __init__(self):
        SCRIPTS_DIR.mkdir(parents=True, exist_ok=True)
        self._executor = PowerShellExecutor()

    def _safe_name(self, name: str) -> str:
        return "".join(c for c in name if c.isalnum() or c in ("_", "-"))[:100]

    def _path_for(self, name: str) -> Path:
        return SCRIPTS_DIR / f"{self._safe_name(name)}.ps1"

    def save_script(self, name: str, content: str) -> Dict:
        """Save (or overwrite) a named PowerShell script."""
        if not name or not content:
            return {"error": "name and content must both be non-empty"}
        safe = self._safe_name(name)
        if not safe:
            return {"error": "name must contain at least one alphanumeric character"}
        path = self._path_for(safe)
        overwrote = path.exists()
        try:
            path.write_text(content, encoding="utf-8")
            return {"success": True, "name": safe, "path": str(path), "overwrote": overwrote}
        except Exception as e:
            return {"error": str(e)}

    def list_scripts(self) -> Dict:
        """List all saved scripts."""
        try:
            names = sorted(p.stem for p in SCRIPTS_DIR.glob("*.ps1"))
            return {"success": True, "scripts": names, "count": len(names)}
        except Exception as e:
            return {"error": str(e)}

    def get_script(self, name: str) -> Dict:
        """View a saved script's content."""
        path = self._path_for(name)
        if not path.exists():
            return {"error": f"No saved script named '{name}'"}
        try:
            return {"success": True, "name": path.stem, "content": path.read_text(encoding="utf-8")}
        except Exception as e:
            return {"error": str(e)}

    def delete_script(self, name: str, confirm: bool = False) -> Dict:
        """Delete a saved script. Confirm-gated."""
        path = self._path_for(name)
        if not path.exists():
            return {"error": f"No saved script named '{name}'"}
        if not confirm:
            return {
                "success": False,
                "needs_confirmation": True,
                "preview": f"Would delete saved PowerShell script '{path.stem}'",
                "message": "Call again with confirm=true to apply.",
            }
        try:
            path.unlink()
            return {"success": True, "name": path.stem, "deleted": True}
        except Exception as e:
            return {"error": str(e)}

    def run_script(self, name: str, timeout: int = 60, confirm: bool = False) -> Dict:
        """Run a saved script by name. Delegates to PowerShellExecutor's
        run_script_file, so the same dangerous-command blocklist and
        output-capture apply as for any ad-hoc .ps1. Confirm-gated -
        this executes whatever the script contains."""
        path = self._path_for(name)
        if not path.exists():
            return {"error": f"No saved script named '{name}'"}
        if not confirm:
            preview = path.read_text(encoding="utf-8")[:200]
            return {
                "success": False,
                "needs_confirmation": True,
                "preview": f"Would run '{path.stem}':\n{preview}",
                "message": "Call again with confirm=true to apply.",
            }
        return self._executor.run_script_file(str(path), timeout=timeout)

    def run_adhoc(self, script: str, timeout: int = 30) -> Dict:
        """Run a one-off PowerShell command/script string without saving
        it. Thin passthrough to PowerShellExecutor.run_powershell - kept
        here too so callers only need this one manager for every
        PowerShell need (saved or not)."""
        return self._executor.run_powershell(script, timeout=timeout)

    def get_execution_policy(self, scope: str = "CurrentUser") -> Dict:
        """Read the effective PowerShell execution policy for a scope
        (Process/CurrentUser/LocalMachine/...)."""
        result = self._executor.run_powershell(f"Get-ExecutionPolicy -Scope {scope}")
        if "error" in result:
            return result
        if not result.get("success"):
            return {"error": result.get("stderr") or "Get-ExecutionPolicy failed"}
        return {"success": True, "scope": scope, "policy": result["stdout"].strip()}

    def set_execution_policy(self, policy: str, scope: str = "CurrentUser", confirm: bool = False) -> Dict:
        """Set the PowerShell execution policy for a scope. Confirm-gated -
        loosening this (e.g. to Bypass/Unrestricted) changes what
        scripts are allowed to run system-wide for that scope."""
        if policy not in VALID_POLICIES:
            return {"error": f"policy must be one of {VALID_POLICIES}"}
        if not confirm:
            return {
                "success": False,
                "needs_confirmation": True,
                "preview": f"Would set execution policy to '{policy}' for scope '{scope}'",
                "message": "Call again with confirm=true to apply.",
            }
        result = self._executor.run_powershell(f"Set-ExecutionPolicy -ExecutionPolicy {policy} -Scope {scope} -Force")
        if "error" in result:
            return result
        if not result.get("success"):
            return {"error": result.get("stderr") or "Set-ExecutionPolicy failed - may need Administrator"}
        return {"success": True, "policy": policy, "scope": scope}
