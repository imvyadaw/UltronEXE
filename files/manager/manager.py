"""File manager
=============
List, search, read, create, write, copy, move, delete files & folders.
"""

import os
import glob
import shutil
import ctypes
from pathlib import Path
from typing import Dict
from datetime import datetime

try:
    from send2trash import send2trash

    HAS_SEND2TRASH = True
except ImportError:
    HAS_SEND2TRASH = False


class FileManager:
    """File & folder operations, scoped to a 'current directory' the user can browse."""

    def __init__(self):
        self.home_dir = Path.home()
        self.current_dir = self.home_dir

    def empty_trash(self) -> Dict:
        """Empty the Windows Recycle Bin."""
        try:
            SHERB_NOCONFIRMATION = 0x00000001
            SHERB_NOPROGRESSUI = 0x00000002
            SHERB_NOSOUND = 0x00000004
            flags = SHERB_NOCONFIRMATION | SHERB_NOPROGRESSUI | SHERB_NOSOUND
            result = ctypes.windll.shell32.SHEmptyRecycleBinW(None, None, flags)
            if result in (0, -2147418113):  # 0 = success, this HRESULT = "already empty"
                return {"success": True, "message": "Recycle Bin emptied"}
            return {"error": f"Failed to empty Recycle Bin (code {result})"}
        except Exception as e:
            return {"error": str(e)}

    def _is_hidden(self, path: Path) -> bool:
        """Windows hidden-file check (attribute based, not dot-prefix)."""
        try:
            FILE_ATTRIBUTE_HIDDEN = 0x2
            attrs = ctypes.windll.kernel32.GetFileAttributesW(str(path))
            if attrs == -1:
                return False
            return bool(attrs & FILE_ATTRIBUTE_HIDDEN)
        except Exception:
            return False

    def list_directory(self, path: str = ".") -> Dict:
        """List contents of a directory."""
        try:
            target_path = self._resolve_path(path)

            if not target_path.exists():
                return {"error": f"Path does not exist: {target_path}"}
            if not target_path.is_dir():
                return {"error": f"Not a directory: {target_path}"}

            files = []
            folders = []

            for item in sorted(target_path.iterdir()):
                if self._is_hidden(item):
                    continue
                if item.is_dir():
                    folders.append(item.name)
                else:
                    size = item.stat().st_size
                    files.append({"name": item.name, "size": self._format_size(size)})

            return {
                "path": str(target_path),
                "folders": folders,
                "files": files,
                "total_items": len(files) + len(folders),
            }

        except PermissionError:
            return {"error": f"Permission denied: {path}"}
        except Exception as e:
            return {"error": str(e)}

    def search_files(self, pattern: str, search_path: str = "~") -> Dict:
        """Search for files matching a pattern."""
        try:
            base_path = self._resolve_path(search_path)

            if "*" not in pattern:
                pattern = f"*{pattern}*"

            matches = []
            search_pattern = str(base_path / "**" / pattern)

            for match in glob.iglob(search_pattern, recursive=True):
                match_path = Path(match)
                if not self._is_hidden(match_path):
                    matches.append(
                        {
                            "path": str(match),
                            "name": match_path.name,
                            "type": "folder" if match_path.is_dir() else "file",
                        }
                    )

                if len(matches) >= 30:
                    break

            return {"pattern": pattern, "matches": matches, "count": len(matches)}

        except Exception as e:
            return {"error": str(e)}

    def find_folder(self, folder_name: str, search_path: str = "~") -> Dict:
        """Find a specific folder by name."""
        try:
            base_path = self._resolve_path(search_path)
            found = []

            for root, dirs, files in os.walk(base_path):
                dirs[:] = [d for d in dirs if not self._is_hidden(Path(root) / d)]

                for d in dirs:
                    if folder_name.lower() in d.lower():
                        full_path = Path(root) / d
                        found.append(
                            {"name": d, "path": str(full_path), "exact_match": d.lower() == folder_name.lower()}
                        )

                if len(found) >= 10:
                    break

            return {"found": found, "count": len(found)}

        except Exception as e:
            return {"error": str(e)}

    def read_file(self, file_path: str, max_lines: int = 50) -> Dict:
        """Read contents of a file."""
        try:
            path = self._resolve_path(file_path)

            if not path.exists():
                return {"error": f"File does not exist: {path}"}
            if path.stat().st_size > 500 * 1024:  # 500KB limit
                return {"error": "File too large"}

            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                lines = f.readlines()[:max_lines]
                content = "".join(lines)

            return {"content": content, "lines_read": len(lines)}

        except Exception as e:
            return {"error": str(e)}

    def get_file_info(self, file_path: str) -> Dict:
        """Get info about a file or folder."""
        try:
            path = self._resolve_path(file_path)

            if not path.exists():
                return {"error": f"Path does not exist: {path}"}

            stat = path.stat()
            return {
                "name": path.name,
                "type": "folder" if path.is_dir() else "file",
                "size": self._format_size(stat.st_size),
                "modified": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M"),
            }

        except Exception as e:
            return {"error": str(e)}

    def create_folder(self, folder_path: str) -> Dict:
        """Create a new folder (and any missing parent folders)."""
        try:
            path = self._resolve_path(folder_path)
            path.mkdir(parents=True, exist_ok=True)
            return {"success": True, "created": str(path)}
        except Exception as e:
            return {"error": str(e)}

    def create_file(self, file_path: str, content: str = "") -> Dict:
        """Create a new file with optional initial content."""
        try:
            path = self._resolve_path(file_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            if path.exists():
                return {"error": f"File already exists: {path} - use write_file to modify it"}
            path.write_text(content, encoding="utf-8")
            return {"success": True, "created": str(path)}
        except Exception as e:
            return {"error": str(e)}

    def write_file(self, file_path: str, content: str, append: bool = False) -> Dict:
        """Write (overwrite) or append text content to a file."""
        try:
            path = self._resolve_path(file_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, "a" if append else "w", encoding="utf-8") as f:
                f.write(content)
            return {"success": True, "written_to": str(path), "mode": "appended" if append else "overwritten"}
        except Exception as e:
            return {"error": str(e)}

    def copy_file(self, source: str, destination: str) -> Dict:
        """Copy a file or folder to a new location."""
        try:
            src, dst = self._resolve_path(source), self._resolve_path(destination)
            if not src.exists():
                return {"error": f"Source not found: {src}"}
            if src.is_dir():
                shutil.copytree(src, dst, dirs_exist_ok=True)
            else:
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)
            return {"success": True, "copied": str(src), "to": str(dst)}
        except Exception as e:
            return {"error": str(e)}

    def move_file(self, source: str, destination: str) -> Dict:
        """Move or rename a file or folder."""
        try:
            src, dst = self._resolve_path(source), self._resolve_path(destination)
            if not src.exists():
                return {"error": f"Source not found: {src}"}
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(src), str(dst))
            return {"success": True, "moved": str(src), "to": str(dst)}
        except Exception as e:
            return {"error": str(e)}

    def delete_file(self, file_path: str) -> Dict:
        """Delete a file - sends it to the Recycle Bin (not permanent)."""
        if not HAS_SEND2TRASH:
            return {"error": "send2trash not installed - run: pip install send2trash"}
        try:
            path = self._resolve_path(file_path)
            if not path.exists():
                return {"error": f"File not found: {path}"}
            if path.is_dir():
                return {"error": f"'{file_path}' is a folder - use delete_folder instead"}
            send2trash(str(path))
            return {"success": True, "deleted": str(path), "note": "Moved to Recycle Bin"}
        except Exception as e:
            return {"error": str(e)}

    def delete_folder(self, folder_path: str) -> Dict:
        """Delete a folder - sends it to the Recycle Bin (not permanent)."""
        if not HAS_SEND2TRASH:
            return {"error": "send2trash not installed - run: pip install send2trash"}
        try:
            path = self._resolve_path(folder_path)
            if not path.exists():
                return {"error": f"Folder not found: {path}"}
            if not path.is_dir():
                return {"error": f"'{folder_path}' is a file - use delete_file instead"}
            send2trash(str(path))
            return {"success": True, "deleted": str(path), "note": "Moved to Recycle Bin"}
        except Exception as e:
            return {"error": str(e)}

    def open_file(self, file_path: str) -> Dict:
        """Open a file with its default Windows application."""
        try:
            path = self._resolve_path(file_path)
            if not path.exists():
                return {"error": f"File not found: {path}"}
            os.startfile(str(path))
            return {"success": True, "opened": str(path)}
        except Exception as e:
            return {"error": str(e)}

    def _resolve_path(self, path: str) -> Path:
        path = os.path.expanduser(path)
        path_obj = Path(path)
        if not path_obj.is_absolute():
            path_obj = self.current_dir / path_obj
        return path_obj.resolve()

    def _format_size(self, size: int) -> str:
        for unit in ["B", "KB", "MB", "GB"]:
            if size < 1024:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} TB"
