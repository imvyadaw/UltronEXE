"""Indexed file search
====================
Builds a lightweight SQLite index of filenames (and optionally text
content of small text files) under a root folder, so repeat searches
don't re-walk the whole disk every time. Falls back gracefully - if
no index has been built yet, `search_files` in files/manager/manager.py
already covers the on-the-fly glob case; this module is for fast,
repeated, larger-scope searches.
"""

import os
import sqlite3
import time
from pathlib import Path
from typing import Dict, List

DB_PATH = Path(__file__).resolve().parents[2] / "storage" / "sqlite" / "file_index.db"

TEXT_EXTENSIONS = {".txt", ".md", ".py", ".json", ".csv", ".log"}
MAX_TEXT_SIZE = 200_000  # don't index content of files bigger than this


class IndexedSearch:
    """SQLite-backed filename + small-text-file content index."""

    def __init__(self):
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
        self._conn.execute("""CREATE TABLE IF NOT EXISTS files (
                path TEXT PRIMARY KEY,
                name TEXT,
                dir TEXT,
                size INTEGER,
                modified REAL,
                content TEXT
            )""")
        self._conn.execute("CREATE INDEX IF NOT EXISTS idx_name ON files(name)")
        self._conn.commit()

    def build_index(self, root_path: str, index_content: bool = False) -> Dict:
        """Walk root_path and (re)build the index. Skips hidden/system folders."""
        try:
            root = Path(root_path).expanduser().resolve()
            if not root.exists():
                return {"error": f"Path does not exist: {root}"}

            count = 0
            start = time.time()
            cur = self._conn.cursor()
            for dirpath, dirnames, filenames in os.walk(root):
                dirnames[:] = [
                    d
                    for d in dirnames
                    if not d.startswith(".")
                    and d not in ("node_modules", "__pycache__", "$RECYCLE.BIN", "System Volume Information")
                ]
                for fname in filenames:
                    full_path = Path(dirpath) / fname
                    try:
                        stat = full_path.stat()
                    except OSError:
                        continue
                    content = None
                    if index_content and full_path.suffix.lower() in TEXT_EXTENSIONS and stat.st_size <= MAX_TEXT_SIZE:
                        try:
                            content = full_path.read_text(errors="ignore")
                        except Exception:
                            content = None
                    cur.execute(
                        "INSERT OR REPLACE INTO files (path, name, dir, size, modified, content) VALUES (?, ?, ?, ?, ?, ?)",
                        (str(full_path), fname, dirpath, stat.st_size, stat.st_mtime, content),
                    )
                    count += 1
            self._conn.commit()
            elapsed = round(time.time() - start, 2)
            return {"success": True, "root": str(root), "files_indexed": count, "seconds": elapsed}
        except Exception as e:
            return {"error": str(e)}

    def search_indexed(self, query: str, search_content: bool = False, limit: int = 50) -> Dict:
        """Search the previously built index by filename (and optionally content)."""
        try:
            cur = self._conn.cursor()
            like_query = f"%{query}%"
            if search_content:
                cur.execute(
                    "SELECT path, size, modified FROM files WHERE name LIKE ? OR content LIKE ? LIMIT ?",
                    (like_query, like_query, limit),
                )
            else:
                cur.execute(
                    "SELECT path, size, modified FROM files WHERE name LIKE ? LIMIT ?",
                    (like_query, limit),
                )
            rows = cur.fetchall()
            results: List[Dict] = [{"path": r[0], "size": r[1], "modified": r[2]} for r in rows]
            return {"query": query, "count": len(results), "results": results}
        except Exception as e:
            return {"error": str(e)}

    def index_stats(self) -> Dict:
        """Report how many files are currently indexed."""
        try:
            cur = self._conn.cursor()
            cur.execute("SELECT COUNT(*) FROM files")
            total = cur.fetchone()[0]
            return {"indexed_files": total, "db_path": str(DB_PATH)}
        except Exception as e:
            return {"error": str(e)}
