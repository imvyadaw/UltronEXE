"""File Recovery
================
Two recovery paths: (1) restoring a file/folder from a backup created
by system_control/files/backup.py, and (2) recovering an item still
sitting in the Windows Recycle Bin (list what's there, restore an item
back to where it was deleted from). Distinct from
self_healing/auto_recovery.py (recovers ULTRON's own process/state,
not user files) and intelligence/goal_manager/recovery_manager.py
(goal-planning recovery, unrelated).

Recycle Bin access goes through the Shell.Application COM object (the
same one Windows Explorer itself uses) via PowerShell - there's no
direct filesystem API for "list/restore recycled items" the way there
is for backups. restore_from_recycle_bin's InvokeVerb("Restore") call
depends on the recycle bin context-menu verb existing under that exact
label on the current Windows locale/build; when it doesn't work this
surfaces as a clear failure rather than silently doing nothing, and
the item can still be recovered manually from the Recycle Bin.

Both restore_from_backup and restore_from_recycle_bin are confirm-
gated - both can overwrite a file at the destination.
"""

import shutil
import subprocess
import zipfile
from pathlib import Path
from typing import Dict

from system_control.files.backup import BACKUP_DIR


class FileRecovery:
    """Restore from a system_control/files/backup.py backup, or from the Recycle Bin."""

    def _run_ps(self, cmd: str, timeout: float = 30.0) -> Dict:
        try:
            result = subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", cmd],
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            return {
                "success": result.returncode == 0,
                "stdout": result.stdout.strip(),
                "stderr": result.stderr.strip(),
            }
        except FileNotFoundError:
            return {"error": "PowerShell not found - this is only available on Windows"}
        except subprocess.TimeoutExpired:
            return {"error": "Command timed out"}
        except Exception as e:
            return {"error": str(e)}

    # ------------------------------------------------------------ backups
    def restore_from_backup(self, backup_path: str, target_path: str, confirm: bool = False) -> Dict:
        """Restore a file/folder backup (created by
        system_control.files.backup.FileBackup) to target_path. .zip
        backups are extracted as a folder; other backups are copied
        back as a single file. Confirm-gated - overwrites target_path if
        it already exists."""
        src = Path(backup_path)
        if not src.exists() or not src.is_file():
            return {"error": f"Backup not found: {backup_path}"}
        try:
            backups_resolved = BACKUP_DIR.resolve()
            src_resolved = src.resolve()
        except Exception as e:
            return {"error": str(e)}
        if src_resolved.parent != backups_resolved:
            return {"error": "backup_path must be a file under ultron_data/file_backups/"}
        if not target_path:
            return {"error": "target_path must be non-empty"}

        dest = Path(target_path)
        is_zip = zipfile.is_zipfile(src)
        if not confirm:
            kind = "folder (extracted from .zip)" if is_zip else "file"
            return {
                "success": False,
                "needs_confirmation": True,
                "preview": f"Would restore {kind} from {src} to {dest} (overwrites destination if it exists)",
                "message": "Call again with confirm=true to apply.",
            }
        try:
            if is_zip:
                dest.mkdir(parents=True, exist_ok=True)
                with zipfile.ZipFile(src) as zf:
                    zf.extractall(dest)
                return {"success": True, "backup_path": str(src), "target_path": str(dest), "type": "folder"}
            else:
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dest)
                return {"success": True, "backup_path": str(src), "target_path": str(dest), "type": "file"}
        except Exception as e:
            return {"error": str(e)}

    # -------------------------------------------------------- recycle bin
    def list_recycle_bin(self) -> Dict:
        """List items currently in the Recycle Bin (name, original path, size)."""
        cmd = (
            "$shell = New-Object -ComObject Shell.Application; "
            "$bin = $shell.Namespace(10); "
            "$items = @(); "
            "foreach ($item in $bin.Items()) { "
            "  $items += [PSCustomObject]@{ Name=$item.Name; Path=$item.Path; "
            "  Size=$item.ExtendedProperty('System.Size') }; "
            "} "
            "$items | ConvertTo-Json"
        )
        result = self._run_ps(cmd)
        if "error" in result:
            return result
        if not result["success"]:
            return {"error": result["stderr"] or "Could not read the Recycle Bin"}
        import json

        try:
            data = json.loads(result["stdout"]) if result["stdout"] else []
            items = data if isinstance(data, list) else [data]
        except Exception as e:
            return {"error": f"Could not parse output: {e}", "raw": result["stdout"]}
        return {"success": True, "items": items, "count": len(items)}

    def restore_from_recycle_bin(self, item_name: str, confirm: bool = False) -> Dict:
        """Restore an item from the Recycle Bin back to where it was
        deleted from, matched by name (from list_recycle_bin). Confirm-
        gated - best-effort: depends on the Recycle Bin's 'Restore'
        context-menu verb being available on this Windows build/locale;
        a clear error is returned if it isn't, and the item can still be
        restored manually from the Recycle Bin in that case."""
        if not item_name:
            return {"error": "item_name must be non-empty"}
        if not confirm:
            return {
                "success": False,
                "needs_confirmation": True,
                "preview": f"Would restore {item_name!r} from the Recycle Bin to its original location",
                "message": "Call again with confirm=true to apply.",
            }
        safe_name = item_name.replace("'", "''")
        cmd = (
            "$shell = New-Object -ComObject Shell.Application; "
            "$bin = $shell.Namespace(10); "
            f"$item = $bin.Items() | Where-Object {{ $_.Name -eq '{safe_name}' }} | Select-Object -First 1; "
            "if ($null -eq $item) { Write-Output 'NOT_FOUND' } "
            "else { $item.InvokeVerb('Restore'); Write-Output 'INVOKED' }"
        )
        result = self._run_ps(cmd)
        if "error" in result:
            return result
        raw = (result.get("stdout") or "").strip()
        if raw == "NOT_FOUND":
            return {"error": f"No item named {item_name!r} found in the Recycle Bin"}
        if not result["success"] or raw != "INVOKED":
            return {
                "error": result.get("stderr")
                or "Could not restore item - the 'Restore' verb may not "
                "be available on this Windows build/locale. Try restoring it manually from "
                "the Recycle Bin."
            }
        return {
            "success": True,
            "item_name": item_name,
            "note": "Restore verb invoked - check the item's original location to confirm.",
        }
