"""File Backup
==============
Point-in-time backup of an arbitrary user-chosen file or folder (zipped
for folders, copied as-is for a single file) into
ultron_data/file_backups/, timestamped so multiple backups of the same
path can coexist. Pairs with system_control/files/recovery.py, which
restores from what this module creates.

Distinct from scripts/backup.py (backs up ULTRON's own SQLite
databases under storage/, a fixed internal set of files) and
system_control/system_config/registry_backup.py (registry keys, not
filesystem paths) - this one is for whatever file/folder the user
points ULTRON at.

backup_path is comparatively low-risk (it only adds a backup, doesn't
touch the original), but confirm-gated anyway for consistency with the
rest of this package and because folder backups can take real time/
disk space.
"""

import shutil
import time
from pathlib import Path
from typing import Dict

BACKUP_DIR = Path("ultron_data") / "file_backups"


class FileBackup:
    """Backup an arbitrary file or folder to a timestamped archive."""

    def _ensure_dir(self) -> Path:
        BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        return BACKUP_DIR

    def _safe_name(self, path: Path) -> str:
        stem = path.name or path.as_posix().replace("/", "_").replace("\\", "_")
        return "".join(c for c in stem if c.isalnum() or c in ("_", "-", "."))[:100] or "backup"

    def backup_path(self, path: str, confirm: bool = False) -> Dict:
        """Back up a file or folder. Folders are zipped; single files are
        copied as-is. Confirm-gated."""
        src = Path(path)
        if not src.exists():
            return {"error": f"Path not found: {path}"}
        if not confirm:
            kind = "folder (as a .zip)" if src.is_dir() else "file"
            return {
                "success": False,
                "needs_confirmation": True,
                "preview": f"Would back up {kind} {src} to {BACKUP_DIR}/",
                "message": "Call again with confirm=true to apply.",
            }
        try:
            out_dir = self._ensure_dir()
            ts = int(time.time())
            base_name = self._safe_name(src)
            if src.is_dir():
                archive_stem = out_dir / f"{base_name}_{ts}"
                archive_path = shutil.make_archive(str(archive_stem), "zip", root_dir=str(src))
                return {
                    "success": True,
                    "source": str(src),
                    "backup_path": archive_path,
                    "type": "folder",
                    "size_bytes": Path(archive_path).stat().st_size,
                }
            else:
                dest = out_dir / f"{base_name}_{ts}{src.suffix}"
                shutil.copy2(src, dest)
                return {
                    "success": True,
                    "source": str(src),
                    "backup_path": str(dest),
                    "type": "file",
                    "size_bytes": dest.stat().st_size,
                }
        except Exception as e:
            return {"error": str(e)}

    def list_backups(self, source_filter: str = "") -> Dict:
        """List previously created file backups, optionally filtered to
        those whose filename contains source_filter."""
        try:
            out_dir = self._ensure_dir()
            files = sorted(out_dir.glob("*"), key=lambda p: p.stat().st_mtime, reverse=True)
            if source_filter:
                files = [f for f in files if source_filter.lower() in f.name.lower()]
            backups = [
                {"backup_path": str(f), "size_bytes": f.stat().st_size, "modified": f.stat().st_mtime} for f in files
            ]
            return {"success": True, "backups": backups, "count": len(backups)}
        except Exception as e:
            return {"error": str(e)}

    def delete_backup(self, backup_path: str, confirm: bool = False) -> Dict:
        """Delete a previously created backup file. Confirm-gated."""
        p = Path(backup_path)
        try:
            p_resolved = p.resolve()
            backups_resolved = BACKUP_DIR.resolve()
        except Exception as e:
            return {"error": str(e)}
        if backups_resolved not in p_resolved.parents and p_resolved.parent != backups_resolved:
            return {"error": "backup_path must be a file under ultron_data/file_backups/"}
        if not p.exists():
            return {"error": f"Backup not found: {backup_path}"}
        if not confirm:
            return {
                "success": False,
                "needs_confirmation": True,
                "preview": f"Would delete backup {p}",
                "message": "Call again with confirm=true to apply.",
            }
        try:
            p.unlink()
            return {"success": True, "backup_path": str(p), "deleted": True}
        except Exception as e:
            return {"error": str(e)}
