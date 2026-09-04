"""Bookmark manager
================
Read, add, search, and delete bookmarks in Chrome/Edge's JSON
bookmarks file directly (both use the same "Bookmarks" format under
their profile folder), plus read-only listing for Firefox, which
stores bookmarks in its places.sqlite database instead. Writing to
Firefox's bookmarks isn't supported here - places.sqlite is locked
while Firefox runs and editing it live risks corrupting the profile.
"""

import json
import shutil
import sqlite3
import tempfile
import uuid
from pathlib import Path
from typing import Dict, List

CHROME_BOOKMARKS_PATH = Path.home() / "AppData/Local/Google/Chrome/User Data/Default/Bookmarks"
EDGE_BOOKMARKS_PATH = Path.home() / "AppData/Local/Microsoft/Edge/User Data/Default/Bookmarks"
FIREFOX_PROFILES_DIR = Path.home() / "AppData/Roaming/Mozilla/Firefox/Profiles"


def _path_for(browser: str) -> Path:
    return CHROME_BOOKMARKS_PATH if browser.lower() == "chrome" else EDGE_BOOKMARKS_PATH


class BookmarkManager:
    """Read/write Chrome & Edge bookmarks; read-only for Firefox."""

    def _load(self, browser: str) -> Dict:
        path = _path_for(browser)
        if not path.exists():
            return {"error": f"{browser} bookmarks file not found at {path}"}
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    def _save(self, browser: str, data: Dict) -> None:
        path = _path_for(browser)
        # Browser must be closed for this write to stick (it rewrites the file
        # from memory on exit) - still useful for adding bookmarks the browser
        # will pick up next launch, or while the browser happens to be closed.
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=3)

    def _walk(self, node: Dict, folder_path: str = "") -> List[Dict]:
        results = []
        node_type = node.get("type")
        if node_type == "url":
            results.append(
                {"name": node.get("name"), "url": node.get("url"), "folder": folder_path, "id": node.get("id")}
            )
        elif node_type == "folder":
            child_path = f"{folder_path}/{node.get('name', '')}".strip("/")
            for child in node.get("children", []):
                results.extend(self._walk(child, child_path))
        return results

    def list_bookmarks(self, browser: str = "chrome") -> Dict:
        """List every bookmark (name, url, containing folder) for chrome/edge."""
        data = self._load(browser)
        if "error" in data:
            return data
        roots = data.get("roots", {})
        results = []
        for root_name, root_node in roots.items():
            if isinstance(root_node, dict):
                results.extend(self._walk(root_node, root_node.get("name", root_name)))
        return {"browser": browser, "count": len(results), "bookmarks": results}

    def search_bookmarks(self, query: str, browser: str = "chrome") -> Dict:
        """Search bookmark names/URLs for a substring."""
        listing = self.list_bookmarks(browser)
        if "error" in listing:
            return listing
        query_lower = query.lower()
        matches = [
            b
            for b in listing["bookmarks"]
            if query_lower in (b["name"] or "").lower() or query_lower in (b["url"] or "").lower()
        ]
        return {"query": query, "browser": browser, "count": len(matches), "matches": matches}

    def add_bookmark(self, name: str, url: str, browser: str = "chrome", folder: str = "Bookmarks bar") -> Dict:
        """Add a bookmark to the given top-level folder ('Bookmarks bar' or
        'Other bookmarks'). Close the browser first so the write isn't
        overwritten on next exit."""
        data = self._load(browser)
        if "error" in data:
            return data
        roots = data.get("roots", {})
        target_key = "bookmark_bar" if "bar" in folder.lower() else "other"
        if target_key not in roots:
            return {"error": f"Could not find a '{folder}' root in the bookmarks file"}

        new_id = str(
            max(
                (
                    int(b.get("id", 0))
                    for b in self._walk(roots.get("bookmark_bar", {})) + self._walk(roots.get("other", {}))
                    if str(b.get("id", "0")).isdigit()
                ),
                default=1000,
            )
            + 1
        )
        new_node = {"type": "url", "name": name, "url": url, "id": new_id, "guid": str(uuid.uuid4())}
        roots[target_key].setdefault("children", []).append(new_node)
        self._save(browser, data)
        return {"success": True, "name": name, "url": url, "folder": folder, "browser": browser}

    def delete_bookmark(self, name: str, browser: str = "chrome") -> Dict:
        """Delete the first bookmark whose name matches exactly. Close the
        browser first so the write isn't overwritten on next exit."""
        data = self._load(browser)
        if "error" in data:
            return data
        roots = data.get("roots", {})

        def remove_from(node: Dict) -> bool:
            children = node.get("children")
            if not children:
                return False
            for i, child in enumerate(children):
                if child.get("type") == "url" and child.get("name") == name:
                    children.pop(i)
                    return True
                if child.get("type") == "folder" and remove_from(child):
                    return True
            return False

        removed = any(remove_from(root) for root in roots.values() if isinstance(root, dict))
        if not removed:
            return {"error": f"No bookmark named '{name}' found"}
        self._save(browser, data)
        return {"success": True, "deleted": name, "browser": browser}

    def list_firefox_bookmarks(self, limit: int = 100) -> Dict:
        """Read-only: list bookmarks from Firefox's places.sqlite (default profile)."""
        try:
            if not FIREFOX_PROFILES_DIR.exists():
                return {"error": f"Firefox profiles dir not found at {FIREFOX_PROFILES_DIR}"}
            profiles = [p for p in FIREFOX_PROFILES_DIR.iterdir() if p.is_dir() and p.name.endswith(".default-release")]
            if not profiles:
                profiles = [p for p in FIREFOX_PROFILES_DIR.iterdir() if p.is_dir()]
            if not profiles:
                return {"error": "No Firefox profile found"}
            places_path = profiles[0] / "places.sqlite"
            if not places_path.exists():
                return {"error": f"places.sqlite not found in profile {profiles[0]}"}

            with tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False) as tmp:
                tmp_path = tmp.name
            shutil.copy2(places_path, tmp_path)

            conn = sqlite3.connect(tmp_path)
            cur = conn.cursor()
            cur.execute(
                """
                SELECT moz_bookmarks.title, moz_places.url
                FROM moz_bookmarks
                JOIN moz_places ON moz_bookmarks.fk = moz_places.id
                WHERE moz_bookmarks.type = 1 AND moz_bookmarks.title IS NOT NULL
                ORDER BY moz_bookmarks.dateAdded DESC LIMIT ?
            """,
                (limit,),
            )
            rows = cur.fetchall()
            conn.close()
            Path(tmp_path).unlink(missing_ok=True)

            bookmarks = [{"name": r[0], "url": r[1]} for r in rows]
            return {"browser": "firefox", "count": len(bookmarks), "bookmarks": bookmarks}
        except Exception as e:
            return {"error": str(e)}
