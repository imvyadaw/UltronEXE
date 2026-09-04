"""File Sync
============
Folder-to-folder sync via `robocopy` (built into every modern Windows
install, no extra dependency) - one-way copy of new/changed files, or
full mirror (also deletes files in the destination that no longer
exist in the source). This is local/network-path sync driven directly
by ULTRON, distinct from apps/cloud/_sync_folder_base.py (which hands
files to a third-party client's own sync folder and lets *that*
software do the syncing) and devices/sync_all.py (which fans out
status reads across phone/watch/TV/car links - no file copying at all).

preview_sync always runs first (robocopy's own /L "list only" dry-run
mode) so the caller can see what would change; sync_folders is
confirm-gated on top of that, and mirror=True gets an extra-explicit
warning in the preview since it deletes files, not just copies them.
"""

import subprocess
from pathlib import Path
from typing import Dict


class FileSync:
    """One-way or mirror folder sync via robocopy."""

    def _run_robocopy(self, args: list, timeout: float = 300.0) -> Dict:
        try:
            result = subprocess.run(
                ["robocopy"] + args,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            # robocopy's exit codes are a bitmask where 0-7 all mean
            # "success, some files copied/skipped" - only >=8 is a real
            # failure. See Microsoft's robocopy exit-code table.
            success = result.returncode < 8
            return {
                "success": success,
                "return_code": result.returncode,
                "stdout": result.stdout.strip(),
                "stderr": result.stderr.strip(),
            }
        except FileNotFoundError:
            return {"error": "robocopy not found - this is only available on Windows"}
        except subprocess.TimeoutExpired:
            return {"error": f"Sync timed out after {timeout}s"}
        except Exception as e:
            return {"error": str(e)}

    def preview_sync(self, source: str, destination: str, mirror: bool = False) -> Dict:
        """Dry-run a sync (robocopy /L - lists what would change without
        touching anything) so the caller can review before committing."""
        src = Path(source)
        if not src.exists() or not src.is_dir():
            return {"error": f"Source folder not found: {source}"}
        args = [str(src), str(Path(destination)), "/E", "/L", "/NP", "/FP"]
        if mirror:
            args.append("/MIR")
        result = self._run_robocopy(args)
        if "error" in result:
            return result
        return {
            "success": result["success"],
            "source": source,
            "destination": destination,
            "mirror": mirror,
            "preview_output": result["stdout"],
            "return_code": result["return_code"],
        }

    def sync_folders(self, source: str, destination: str, mirror: bool = False, confirm: bool = False) -> Dict:
        """Sync source -> destination. mirror=False copies new/changed
        files only (nothing in destination is ever deleted); mirror=True
        makes destination an exact copy of source (deletes files in
        destination that don't exist in source). Confirm-gated - the
        preview calls out the delete behavior explicitly when
        mirror=True."""
        src = Path(source)
        if not src.exists() or not src.is_dir():
            return {"error": f"Source folder not found: {source}"}
        if not destination:
            return {"error": "destination must be non-empty"}
        if not confirm:
            warning = (
                " This DELETES files in the destination that don't exist in the source."
                if mirror
                else " Only copies new/changed files - nothing is deleted."
            )
            return {
                "success": False,
                "needs_confirmation": True,
                "preview": f"Would sync {src} -> {destination} (mirror={mirror}).{warning}",
                "message": "Call again with confirm=true to apply.",
            }
        args = [str(src), str(destination), "/E", "/NP", "/FP"]
        if mirror:
            args.append("/MIR")
        result = self._run_robocopy(args)
        if "error" in result:
            return result
        return {
            "success": result["success"],
            "source": source,
            "destination": destination,
            "mirror": mirror,
            "output": result["stdout"],
            "return_code": result["return_code"],
        }
