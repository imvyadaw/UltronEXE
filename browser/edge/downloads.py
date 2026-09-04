"""
Edge downloads
================
Edge-specific download history straight from its own SQLite History
file (Edge is Chromium-based, so this is the same query as Chrome's
just against Edge's profile), plus the shared Downloads-folder
operations. For a single call that covers Chrome, Edge, and Firefox
together, see browser/automation/download_manager.py.
"""

import os
import shutil
import sqlite3
import tempfile
import time
from pathlib import Path
from typing import Dict, Optional

EDGE_HISTORY_PATH = Path.home() / "AppData/Local/Microsoft/Edge/User Data/Default/History"


class EdgeDownloads:
    """List/open/clean up downloads, plus Edge's own download history."""

    def _downloads_dir(self) -> Path:
        return Path.home() / "Downloads"

    def list_downloads(self, limit: int = 30) -> Dict:
        """List files in the Downloads folder, most recent first."""
        try:
            downloads = self._downloads_dir()
            if not downloads.exists():
                return {"error": f"Downloads folder not found: {downloads}"}
            files = sorted(downloads.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True)
            files = [f for f in files if f.is_file()][:limit]
            results = [
                {"name": f.name, "size_kb": round(f.stat().st_size / 1024, 1), "modified": f.stat().st_mtime}
                for f in files
            ]
            return {"downloads_folder": str(downloads), "count": len(results), "files": results}
        except Exception as e:
            return {"error": str(e)}

    def open_download(self, filename: str) -> Dict:
        """Open a file from the Downloads folder with its default app."""
        try:
            path = self._downloads_dir() / filename
            if not path.exists():
                return {"error": f"File not found in Downloads: {filename}"}
            os.startfile(str(path))
            return {"success": True, "opened": str(path)}
        except AttributeError:
            return {"error": "os.startfile is only available on Windows"}
        except Exception as e:
            return {"error": str(e)}

    def clear_downloads(self, older_than_days: Optional[int] = None, confirm: bool = False) -> Dict:
        """Delete files from Downloads. Safety-gated: needs confirm=true."""
        if not confirm:
            return {"error": "This permanently deletes files from Downloads. Call again with confirm=true to proceed."}
        try:
            downloads = self._downloads_dir()
            deleted = []
            cutoff = time.time() - (older_than_days * 86400) if older_than_days else None
            for f in downloads.iterdir():
                if not f.is_file():
                    continue
                if cutoff and f.stat().st_mtime > cutoff:
                    continue
                f.unlink()
                deleted.append(f.name)
            return {"success": True, "deleted_count": len(deleted), "deleted": deleted}
        except Exception as e:
            return {"error": str(e)}

    def download_history(self, limit: int = 20) -> Dict:
        """Read recent download history (filename + source URL) straight
        from Edge's History SQLite file. Copies the file first since it's
        locked while Edge is running."""
        try:
            if not EDGE_HISTORY_PATH.exists():
                return {"error": f"Edge history file not found at {EDGE_HISTORY_PATH}"}
            with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
                tmp_path = tmp.name
            shutil.copy2(EDGE_HISTORY_PATH, tmp_path)
            conn = sqlite3.connect(tmp_path)
            cur = conn.cursor()
            cur.execute(
                "SELECT target_path, tab_url, start_time FROM downloads ORDER BY start_time DESC LIMIT ?",
                (limit,),
            )
            rows = cur.fetchall()
            conn.close()
            os.unlink(tmp_path)
            downloads = [{"file": r[0], "source_url": r[1], "start_time": r[2]} for r in rows]
            return {"browser": "edge", "count": len(downloads), "downloads": downloads}
        except Exception as e:
            return {"error": str(e)}

    def search_downloads(self, query: str, limit: int = 20) -> Dict:
        """Search Edge's download history for a filename/URL substring."""
        history = self.download_history(limit=200)
        if "error" in history:
            return history
        q = query.lower()
        matches = [
            d
            for d in history["downloads"]
            if q in (d.get("file") or "").lower() or q in (d.get("source_url") or "").lower()
        ][:limit]
        return {"query": query, "browser": "edge", "count": len(matches), "matches": matches}
