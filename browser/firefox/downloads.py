"""
Firefox downloads
====================
Firefox-specific download history. Unlike Chrome/Edge (which have a
dedicated `downloads` table), Firefox stores download metadata as
annotations on the page in places.sqlite (moz_annos, keyed by
"downloads/destinationFileURI" and "downloads/metaData") - so the query
shape here is genuinely different, not just a path swap. Also exposes
the same shared Downloads-folder operations as the Chrome/Edge modules.
"""

import os
import shutil
import sqlite3
import tempfile
import time
from pathlib import Path
from typing import Dict, Optional

FIREFOX_PROFILES_DIR = Path.home() / "AppData/Roaming/Mozilla/Firefox/Profiles"


def _default_profile() -> Optional[Path]:
    if not FIREFOX_PROFILES_DIR.exists():
        return None
    profiles = [p for p in FIREFOX_PROFILES_DIR.iterdir() if p.is_dir() and p.name.endswith(".default-release")]
    if not profiles:
        profiles = [p for p in FIREFOX_PROFILES_DIR.iterdir() if p.is_dir()]
    return profiles[0] if profiles else None


class FirefoxDownloads:
    """List/open/clean up downloads, plus Firefox's own download history."""

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
        """Read recent download history (filename + source page URL) from
        Firefox's places.sqlite moz_annos table. Copies the file first
        since it's locked while Firefox is running."""
        try:
            profile = _default_profile()
            if not profile:
                return {"error": f"No Firefox profile found under {FIREFOX_PROFILES_DIR}"}
            places_path = profile / "places.sqlite"
            if not places_path.exists():
                return {"error": f"places.sqlite not found in profile {profile}"}

            with tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False) as tmp:
                tmp_path = tmp.name
            shutil.copy2(places_path, tmp_path)

            conn = sqlite3.connect(tmp_path)
            cur = conn.cursor()
            cur.execute(
                """
                SELECT moz_places.url, moz_annos.content, moz_annos.dateAdded
                FROM moz_annos
                JOIN moz_anno_attributes ON moz_annos.anno_attribute_id = moz_anno_attributes.id
                JOIN moz_places ON moz_annos.place_id = moz_places.id
                WHERE moz_anno_attributes.name = 'downloads/destinationFileURI'
                ORDER BY moz_annos.dateAdded DESC LIMIT ?
            """,
                (limit,),
            )
            rows = cur.fetchall()
            conn.close()
            os.unlink(tmp_path)

            downloads = [{"source_url": r[0], "destination": r[1], "date_added": r[2]} for r in rows]
            return {"browser": "firefox", "count": len(downloads), "downloads": downloads}
        except Exception as e:
            return {"error": str(e)}

    def search_downloads(self, query: str, limit: int = 20) -> Dict:
        """Search Firefox's download history for a filename/URL substring."""
        history = self.download_history(limit=200)
        if "error" in history:
            return history
        q = query.lower()
        matches = [
            d
            for d in history["downloads"]
            if q in (d.get("destination") or "").lower() or q in (d.get("source_url") or "").lower()
        ][:limit]
        return {"query": query, "browser": "firefox", "count": len(matches), "matches": matches}
