"""
Cross-browser download manager
=================================
Unifies Chrome/Edge/Firefox download history into one call (composing
browser/chrome/downloads.py, browser/edge/downloads.py, and
browser/firefox/downloads.py instead of re-parsing each browser's
store), plus genuinely new capabilities none of the per-browser
modules have on their own: waiting for an in-progress download to
finish, and organizing the shared Downloads folder by file type.
"""

import time
from pathlib import Path
from typing import Dict, List, Optional

from browser.chrome.downloads import ChromeDownloads
from browser.edge.downloads import EdgeDownloads
from browser.firefox.downloads import FirefoxDownloads

_EXTENSION_FOLDERS = {
    "images": {".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg", ".bmp"},
    "documents": {".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".txt", ".csv"},
    "archives": {".zip", ".rar", ".7z", ".tar", ".gz"},
    "installers": {".exe", ".msi"},
    "audio": {".mp3", ".wav", ".flac", ".m4a"},
    "video": {".mp4", ".mkv", ".avi", ".mov"},
}


class DownloadManager:
    """Cross-browser download history, folder watching, and organizing."""

    def __init__(self):
        self._chrome = ChromeDownloads()
        self._edge = EdgeDownloads()
        self._firefox = FirefoxDownloads()

    def _downloads_dir(self) -> Path:
        return Path.home() / "Downloads"

    def get_all_download_history(self, limit_per_browser: int = 20) -> Dict:
        """Every browser's download history in one call, tagged by browser."""
        results = {}
        for name, tool in [("chrome", self._chrome), ("edge", self._edge), ("firefox", self._firefox)]:
            try:
                results[name] = tool.download_history(limit=limit_per_browser)
            except Exception as e:
                results[name] = {"error": str(e)}
        total = sum(r.get("count", 0) for r in results.values() if isinstance(r, dict))
        return {"by_browser": results, "total": total}

    def list_downloads(self, limit: int = 30) -> Dict:
        """List files in the shared Downloads folder (same folder for
        every browser by default), most recent first."""
        return self._chrome.list_downloads(limit=limit)

    def get_latest_download(self) -> Dict:
        """The single most recently modified file in the Downloads folder."""
        listing = self.list_downloads(limit=1)
        if "error" in listing:
            return listing
        if not listing["files"]:
            return {"success": False, "error": "Downloads folder is empty"}
        return {"success": True, "file": listing["files"][0]}

    def wait_for_download(self, timeout: float = 60.0, name_contains: Optional[str] = None) -> Dict:
        """Poll the Downloads folder until a new file appears (optionally
        matching name_contains), or timeout. Useful right after triggering
        a download so the next step can rely on the file actually being
        there - also skips Chrome/Edge's in-progress `.crdownload` /
        Firefox's `.part` files, waiting for the finished file instead."""
        downloads_dir = self._downloads_dir()
        if not downloads_dir.exists():
            return {"error": f"Downloads folder not found: {downloads_dir}"}
        seen = {f.name for f in downloads_dir.iterdir() if f.is_file()}
        deadline = time.time() + timeout
        while time.time() < deadline:
            current = [f for f in downloads_dir.iterdir() if f.is_file()]
            for f in current:
                if f.name in seen:
                    continue
                if f.suffix in (".crdownload", ".part", ".tmp"):
                    continue
                if name_contains and name_contains.lower() not in f.name.lower():
                    continue
                return {"success": True, "file": f.name, "path": str(f)}
            time.sleep(1.0)
        return {"success": False, "error": f"No new download appeared within {timeout}s"}

    def organize_downloads(self, dry_run: bool = True) -> Dict:
        """Sort files in Downloads into images/documents/archives/installers/
        audio/video subfolders by extension. dry_run=True (default) just
        previews the moves; call with dry_run=False to actually move them."""
        downloads_dir = self._downloads_dir()
        if not downloads_dir.exists():
            return {"error": f"Downloads folder not found: {downloads_dir}"}
        plan: List[Dict] = []
        try:
            for f in downloads_dir.iterdir():
                if not f.is_file():
                    continue
                category = next((cat for cat, exts in _EXTENSION_FOLDERS.items() if f.suffix.lower() in exts), None)
                if not category:
                    continue
                plan.append({"file": f.name, "to_folder": category})
                if not dry_run:
                    dest_dir = downloads_dir / category
                    dest_dir.mkdir(exist_ok=True)
                    f.rename(dest_dir / f.name)
            return {"success": True, "dry_run": dry_run, "planned_moves": len(plan), "moves": plan}
        except Exception as e:
            return {"error": str(e)}

    def clear_all_downloads(self, older_than_days: Optional[int] = None, confirm: bool = False) -> Dict:
        """Delete files from the shared Downloads folder. Safety-gated:
        needs confirm=true."""
        return self._chrome.clear_downloads(older_than_days=older_than_days, confirm=confirm)
