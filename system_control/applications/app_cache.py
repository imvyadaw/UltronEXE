"""App Cache
============
Finds and clears an application's *disposable* cache/temp footprint -
the subset of its data that's safe to delete because the app will just
regenerate it (browser caches, "Cache"/"GPUCache"/"Code Cache"
subfolders, temp files under %TEMP% matching the app's name), as
opposed to state that would lose user data if deleted.

Distinct from app_data_backup.py (that module treats an app's whole
AppData footprint as precious and archives it; this one specifically
targets folders conventionally named as caches and deletes them
outright, no archive) and from storage_sense.py (system_control/
storage/, which runs Windows' own scheduled cleanup across the whole
disk rather than one named app). Also distinct from browser-specific
history/cookie clearing (a browser-automation concern, not a
filesystem one) - this only removes files, it doesn't reset in-app
settings.

Clearing is confirm-gated: some apps store more than they should in a
folder literally named "Cache" (rare, but seen with a few Electron
apps), so this always previews what it found and its size before
deleting.
"""
import logging

import os
import shutil
from typing import Dict, List

_CACHE_FOLDER_NAMES = {
    "cache",
    "gpucache",
    "code cache",
    "cachestorage",
    "dawncache",
    "shadercache",
    "component_crx_cache",
    "cached_theme",
    "thumbnails",
}


class AppCacheManager:
    """Find and clear an application's cache/temp folders."""

    def _appdata_roots(self) -> List[str]:
        roots = [os.environ.get("LOCALAPPDATA"), os.environ.get("APPDATA")]
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

    def _find_app_root(self, app_name: str) -> List[str]:
        matches = []
        for root in self._appdata_roots():
            try:
                for entry in os.listdir(root):
                    if app_name.lower() in entry.lower():
                        full = os.path.join(root, entry)
                        if os.path.isdir(full):
                            matches.append(full)
            except OSError:
                continue
        return matches

    def get_cache_size(self, app_name: str) -> Dict:
        """Locate cache-named subfolders anywhere under an app's
        AppData folder(s) and report their combined size, without
        deleting anything. No admin needed."""
        app_roots = self._find_app_root(app_name)
        if not app_roots:
            return {"error": f"No AppData folder found matching '{app_name}'."}

        cache_dirs = []
        for app_root in app_roots:
            for dirpath, dirnames, _ in os.walk(app_root):
                for d in list(dirnames):
                    if d.lower() in _CACHE_FOLDER_NAMES:
                        full = os.path.join(dirpath, d)
                        cache_dirs.append({"path": full, "size_bytes": self._dir_size(full)})

        temp_dir = os.environ.get("TEMP")
        temp_matches = []
        if temp_dir and os.path.isdir(temp_dir):
            try:
                for entry in os.listdir(temp_dir):
                    if app_name.lower() in entry.lower():
                        full = os.path.join(temp_dir, entry)
                        size = self._dir_size(full) if os.path.isdir(full) else os.path.getsize(full)
                        temp_matches.append({"path": full, "size_bytes": size})
            except OSError:
                logging.getLogger(__name__).exception("Suppressed OSError")

        total = sum(c["size_bytes"] for c in cache_dirs) + sum(t["size_bytes"] for t in temp_matches)
        return {
            "app_name": app_name,
            "cache_folders": cache_dirs,
            "temp_entries": temp_matches,
            "total_size_bytes": total,
        }

    def clear_app_cache(self, app_name: str, confirm: bool = False) -> Dict:
        """Delete every cache-named subfolder and matching %TEMP%
        entry found for an app. Confirm-gated and irreversible - close
        the app first, since files it currently has open may fail to
        delete or be recreated immediately."""
        found = self.get_cache_size(app_name)
        if "error" in found:
            return found

        all_paths = [c["path"] for c in found["cache_folders"]] + [t["path"] for t in found["temp_entries"]]
        if not all_paths:
            return {"app_name": app_name, "cleared": [], "message": "No cache folders found for this app."}

        if not confirm:
            return {
                "requires_confirmation": True,
                "preview": f"This will delete {len(all_paths)} cache folder(s)/file(s) "
                f"(~{found['total_size_bytes'] // (1024 * 1024)} MB) for '{app_name}'.",
                "paths": all_paths,
            }

        cleared, failed = [], []
        for path in all_paths:
            try:
                if os.path.isdir(path):
                    shutil.rmtree(path)
                elif os.path.isfile(path):
                    os.remove(path)
                cleared.append(path)
            except Exception as e:
                failed.append({"path": path, "error": str(e)})

        return {
            "app_name": app_name,
            "cleared": cleared,
            "failed": failed,
            "freed_bytes_approx": found["total_size_bytes"],
        }

    def clear_windows_store_cache(self, confirm: bool = False) -> Dict:
        """Reset the Microsoft Store app's own cache via the built-in
        `wsreset.exe` tool (distinct from clearing a Store *app's*
        cache - this resets the Store client itself, useful when the
        Store fails to show updates/downloads). Confirm-gated since it
        closes and relaunches the Store."""
        if not confirm:
            return {
                "requires_confirmation": True,
                "preview": "This will reset the Microsoft Store app's cache via wsreset.exe.",
            }
        import subprocess

        try:
            subprocess.Popen(["wsreset.exe"], shell=False)
            return {
                "success": True,
                "message": "wsreset.exe launched - the Store will reopen once its cache is cleared.",
            }
        except FileNotFoundError:
            return {"error": "wsreset.exe not found - this is only available on Windows with the Store installed."}
        except Exception as e:
            return {"error": str(e)}
