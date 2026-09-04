"""App Data Backup
==================
App-aware backup/restore of one application's user data - discovers
where an app keeps its state (%LOCALAPPDATA%, %APPDATA%, %LOCALAPPDATA%
\\...\\LocalLow) by name match, and archives it to a single zip so it
can be restored later or carried to another machine.

Distinct from system_control/files/backup.py (which backs up arbitrary
user-chosen folders with no app awareness) - this module's whole job
is the discovery step: given just an app name, find its scattered
data folders across all three AppData roots without the caller having
to know the vendor's folder-naming convention. Also distinct from
app_cache.py (which targets *disposable* cache/temp subfolders
specifically, not full app state) and from system_control/security/
bitlocker_manager.py (whole-volume encryption, unrelated layer).

backup_app_data reads live files that may be open by a running app, so
results can be inconsistent for an app that's actively writing;
restore_app_data overwrites existing data outright. Both are
confirm-gated.
"""
import logging

import os
import shutil
import zipfile
from datetime import datetime
from typing import Dict, List


class AppDataBackup:
    """Discover, back up, and restore an application's AppData folders."""

    def _appdata_roots(self) -> List[str]:
        roots = [
            os.environ.get("LOCALAPPDATA"),
            os.environ.get("APPDATA"),
        ]
        local = os.environ.get("LOCALAPPDATA")
        if local:
            roots.append(os.path.join(local, "..", "LocalLow"))
        return [os.path.normpath(r) for r in roots if r and os.path.isdir(r)]

    @staticmethod
    def _dir_size(path: str) -> int:
        total = 0
        for dirpath, _, filenames in os.walk(path):
            for f in filenames:
                try:
                    total += os.path.getsize(os.path.join(dirpath, f))
                except OSError:
                    logging.getLogger(__name__).exception("Suppressed OSError")
        return total

    def discover_app_data_paths(self, app_name: str) -> Dict:
        """Find every top-level folder under the AppData roots whose
        name (partially, case-insensitively) matches app_name. No
        admin needed."""
        matches = []
        for root in self._appdata_roots():
            try:
                for entry in os.listdir(root):
                    if app_name.lower() in entry.lower():
                        full = os.path.join(root, entry)
                        if os.path.isdir(full):
                            matches.append(
                                {
                                    "path": full,
                                    "root": root,
                                    "approx_size_bytes": self._dir_size(full),
                                }
                            )
            except OSError:
                continue
        return {"app_name": app_name, "paths": matches, "count": len(matches)}

    def backup_app_data(self, app_name: str, destination_path: str, confirm: bool = False) -> Dict:
        """Zip up every discovered AppData folder for app_name into a
        single archive at destination_path. Confirm-gated - reads
        (potentially large) live application state; close the app
        first for a consistent snapshot."""
        found = self.discover_app_data_paths(app_name)
        if not found["paths"]:
            return {"error": f"No AppData folders found matching '{app_name}'."}

        if not confirm:
            total_bytes = sum(p["approx_size_bytes"] for p in found["paths"])
            return {
                "requires_confirmation": True,
                "preview": f"This will back up {found['count']} folder(s) (~{total_bytes // (1024 * 1024)} MB) "
                f"for '{app_name}' to {destination_path}.",
                "paths": [p["path"] for p in found["paths"]],
            }

        os.makedirs(os.path.dirname(os.path.abspath(destination_path)) or ".", exist_ok=True)
        try:
            with zipfile.ZipFile(destination_path, "w", zipfile.ZIP_DEFLATED) as zf:
                zf.writestr(
                    "_manifest.txt",
                    f"app_name={app_name}\ncreated={datetime.now().isoformat()}\n"
                    + "\n".join(p["path"] for p in found["paths"]),
                )
                for entry in found["paths"]:
                    src = entry["path"]
                    arc_root = os.path.basename(os.path.dirname(src)) + "_" + os.path.basename(src)
                    for dirpath, _, filenames in os.walk(src):
                        for f in filenames:
                            file_path = os.path.join(dirpath, f)
                            arcname = os.path.join(arc_root, os.path.relpath(file_path, src))
                            try:
                                zf.write(file_path, arcname)
                            except OSError:
                                continue
        except Exception as e:
            return {"error": str(e)}

        return {
            "success": True,
            "app_name": app_name,
            "destination_path": destination_path,
            "folders_backed_up": found["count"],
            "archive_size_bytes": os.path.getsize(destination_path),
        }

    def list_backups(self, backup_dir: str) -> Dict:
        """List app-data-backup zips in a folder, reading each
        archive's _manifest.txt header. No admin needed."""
        if not os.path.isdir(backup_dir):
            return {"error": f"'{backup_dir}' is not a directory."}
        backups = []
        for entry in os.listdir(backup_dir):
            if not entry.lower().endswith(".zip"):
                continue
            full = os.path.join(backup_dir, entry)
            info = {"file": full, "size_bytes": os.path.getsize(full)}
            try:
                with zipfile.ZipFile(full) as zf:
                    if "_manifest.txt" in zf.namelist():
                        manifest = zf.read("_manifest.txt").decode("utf-8", errors="replace")
                        for line in manifest.splitlines():
                            if line.startswith("app_name="):
                                info["app_name"] = line.split("=", 1)[1]
                            elif line.startswith("created="):
                                info["created"] = line.split("=", 1)[1]
            except (zipfile.BadZipFile, OSError):
                info["error"] = "not a valid app-data-backup archive"
            backups.append(info)
        return {"backups": backups, "count": len(backups)}

    def restore_app_data(self, backup_path: str, confirm: bool = False) -> Dict:
        """Restore a backup created by backup_app_data, overwriting
        any current contents of the same folders. Confirm-gated and
        destructive to whatever's currently there - the app should be
        closed first."""
        if not os.path.isfile(backup_path):
            return {"error": f"Backup file '{backup_path}' not found."}

        if not confirm:
            return {
                "requires_confirmation": True,
                "preview": f"This will restore '{backup_path}', overwriting existing app data at the original paths.",
            }

        try:
            with zipfile.ZipFile(backup_path) as zf:
                manifest_paths = []
                if "_manifest.txt" in zf.namelist():
                    manifest = zf.read("_manifest.txt").decode("utf-8", errors="replace")
                    manifest_paths = [l for l in manifest.splitlines() if l and "=" not in l]

                # Each top-level folder in the archive maps back to
                # <appdata_root>\<original_folder_name>; we recover the
                # root by matching the manifest's recorded original path.
                restored = []
                for arcname in zf.namelist():
                    if arcname == "_manifest.txt" or arcname.endswith("/"):
                        continue
                    top = arcname.split("/", 1)[0]
                    original = next(
                        (
                            p
                            for p in manifest_paths
                            if os.path.basename(os.path.dirname(p)) + "_" + os.path.basename(p) == top
                        ),
                        None,
                    )
                    if not original:
                        continue
                    rel = arcname[len(top) + 1 :]
                    dest = os.path.join(original, rel)
                    os.makedirs(os.path.dirname(dest), exist_ok=True)
                    with zf.open(arcname) as src, open(dest, "wb") as out:
                        shutil.copyfileobj(src, out)
                    restored.append(dest)
        except Exception as e:
            return {"error": str(e)}

        return {"success": True, "backup_path": backup_path, "files_restored": len(restored)}
