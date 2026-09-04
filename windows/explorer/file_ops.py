"""File Explorer control & shell-level file ops
==============================================
Open File Explorer at a path, reveal/select a file, open common shell
locations (This PC, Recycle Bin, Downloads), rename items, inspect
folder sizes, and list drives.

Renamed from explorer/explorer.py (ExplorerTools) as part of Phase 8's
windows/ restructure. Only windows/__init__.py imported the old
module, so this is a clean rename.

Deliberately does NOT duplicate copy/move/delete/create_folder - those
already live in files/manager/manager.py's FileManager (wired as
SystemTools._files) with Recycle-Bin-safe deletes via send2trash.
Adding a second copy/move/delete here would just create two
implementations that could drift apart. This module covers what
FileManager doesn't: driving the actual Explorer shell UI, renaming,
folder-size totals, and drive listing.
"""

import ctypes
import os
import subprocess
from pathlib import Path
from typing import Dict


class ExplorerFileOps:
    """Open/navigate Windows File Explorer plus a few shell-level file ops FileManager doesn't cover."""

    def open_explorer(self, path: str = "~") -> Dict:
        """Open File Explorer at the given folder path."""
        try:
            target = Path(path).expanduser().resolve()
            if not target.exists():
                return {"error": f"Path does not exist: {target}"}
            subprocess.Popen(["explorer", str(target)])
            return {"success": True, "opened": str(target)}
        except Exception as e:
            return {"error": str(e)}

    def reveal_file(self, file_path: str) -> Dict:
        """Open File Explorer with a specific file selected/highlighted."""
        try:
            target = Path(file_path).expanduser().resolve()
            if not target.exists():
                return {"error": f"File does not exist: {target}"}
            subprocess.Popen(["explorer", "/select,", str(target)])
            return {"success": True, "revealed": str(target)}
        except Exception as e:
            return {"error": str(e)}

    def open_special_folder(self, name: str) -> Dict:
        """Open a well-known shell location: 'this_pc', 'recycle_bin', 'downloads',
        'documents', 'desktop', 'pictures', or 'control_panel'."""
        shell_paths = {
            "this_pc": "shell:MyComputerFolder",
            "recycle_bin": "shell:RecycleBinFolder",
            "downloads": "shell:Downloads",
            "documents": "shell:Personal",
            "desktop": "shell:Desktop",
            "pictures": "shell:MyPictures",
            "control_panel": "shell:ControlPanelFolder",
        }
        key = name.lower().replace(" ", "_")
        if key not in shell_paths:
            return {"error": f"Unknown special folder '{name}'. Options: {list(shell_paths)}"}
        try:
            subprocess.Popen(["explorer", shell_paths[key]])
            return {"success": True, "opened": key}
        except Exception as e:
            return {"error": str(e)}

    def rename_item(self, path: str, new_name: str) -> Dict:
        """Rename a file or folder in place (stays in the same parent directory)."""
        try:
            target = Path(path).expanduser().resolve()
            if not target.exists():
                return {"error": f"Path does not exist: {target}"}
            destination = target.parent / new_name
            if destination.exists():
                return {"error": f"'{new_name}' already exists in {target.parent}"}
            target.rename(destination)
            return {"success": True, "old_path": str(target), "new_path": str(destination)}
        except Exception as e:
            return {"error": str(e)}

    def open_properties(self, path: str) -> Dict:
        """Open the native Windows Properties dialog for a file or folder."""
        try:
            target = Path(path).expanduser().resolve()
            if not target.exists():
                return {"error": f"Path does not exist: {target}"}
            # ShellExecute with the "properties" verb is the standard way to
            # trigger this dialog - there's no plain CLI command for it.
            ctypes.windll.shell32.ShellExecuteW(None, "properties", str(target), None, None, 1)
            return {"success": True, "opened_properties_for": str(target)}
        except Exception as e:
            return {"error": str(e)}

    def get_folder_size(self, folder_path: str) -> Dict:
        """Get the total size of a folder (recursive) and how many files/subfolders it contains."""
        try:
            target = Path(folder_path).expanduser().resolve()
            if not target.exists():
                return {"error": f"Folder not found: {target}"}
            if not target.is_dir():
                return {"error": f"'{folder_path}' is a file, not a folder"}
            total_size = 0
            file_count = 0
            folder_count = 0
            for entry in target.rglob("*"):
                try:
                    if entry.is_file():
                        total_size += entry.stat().st_size
                        file_count += 1
                    elif entry.is_dir():
                        folder_count += 1
                except (OSError, PermissionError):
                    continue
            return {
                "path": str(target),
                "size_bytes": total_size,
                "size_readable": self._format_size(total_size),
                "file_count": file_count,
                "folder_count": folder_count,
            }
        except Exception as e:
            return {"error": str(e)}

    def list_drives(self) -> Dict:
        """List available drives with free/total space."""
        try:
            import string

            drives = []
            for letter in string.ascii_uppercase:
                drive = f"{letter}:\\"
                if os.path.exists(drive):
                    try:
                        total, used, free = self._disk_usage(drive)
                        drives.append(
                            {
                                "drive": drive,
                                "total": self._format_size(total),
                                "used": self._format_size(used),
                                "free": self._format_size(free),
                            }
                        )
                    except OSError:
                        drives.append({"drive": drive, "error": "not ready (e.g. empty CD/DVD drive)"})
            return {"count": len(drives), "drives": drives}
        except Exception as e:
            return {"error": str(e)}

    def _disk_usage(self, path: str):
        import shutil

        usage = shutil.disk_usage(path)
        return usage.total, usage.used, usage.free

    def _format_size(self, size: float) -> str:
        for unit in ["B", "KB", "MB", "GB"]:
            if size < 1024:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} TB"
