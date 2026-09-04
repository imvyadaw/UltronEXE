"""Browser downloads
==================
List, open, and clean up files in the default Downloads folder. Also
tries to read Chrome/Edge's download history (source URL, when it was
downloaded) straight from their SQLite History file, for extra detail
when available.
"""

import os
import shutil
import sqlite3
import tempfile
from pathlib import Path
from typing import Dict

CHROME_HISTORY_PATH = Path.home() / "AppData/Local/Google/Chrome/User Data/Default/History"
EDGE_HISTORY_PATH = Path.home() / "AppData/Local/Microsoft/Edge/User Data/Default/History"


class DownloadsTools:
    """List/open/clean up downloaded files."""

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

    def clear_downloads(self, older_than_days: int = None, confirm: bool = False) -> Dict:
        """Delete files from Downloads. If older_than_days is set, only deletes
        files older than that; otherwise deletes everything. Safety-gated: needs confirm=true
        (this is a permanent delete, not a Recycle Bin move)."""
        if not confirm:
            return {"error": "This permanently deletes files from Downloads. Call again with confirm=true to proceed."}
        try:
            import time

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

    def get_download_history(self, browser: str = "chrome", limit: int = 20) -> Dict:
        """Read recent download history (filename + source URL) from Chrome/Edge's
        History SQLite file. Copies the file first since it's locked while the
        browser is running."""
        try:
            history_path = CHROME_HISTORY_PATH if browser.lower() == "chrome" else EDGE_HISTORY_PATH
            if not history_path.exists():
                return {"error": f"{browser} history file not found at {history_path}"}

            with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
                tmp_path = tmp.name
            shutil.copy2(history_path, tmp_path)

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
            return {"browser": browser, "count": len(downloads), "downloads": downloads}
        except Exception as e:
            return {"error": str(e)}
