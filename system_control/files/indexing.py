"""File Indexing
================
A lightweight local filename index (sqlite-backed, ultron_data/file_index/
index.db) so ULTRON can answer "find me that file" instantly instead of
walking the disk on every request. Distinct from files/search (top-level
package, live filesystem search / content grep for one-off queries) and
from intelligence/knowledge_os (which indexes document *content* for
retrieval) - this is purely a name/path/metadata index, rebuilt on demand
per root folder.

Building is the only slow/disruptive operation (a big root can take a
while and replaces any previously indexed rows for that same root), so
build_index and clear_index are confirm-gated like every other
state-changing tool in this codebase; search/stat reads are not.
"""

import os
import sqlite3
import time
from pathlib import Path
from typing import Dict, List, Optional

INDEX_DIR = Path("ultron_data") / "file_index"
INDEX_DB = INDEX_DIR / "index.db"

# Directories that are almost never useful to index and routinely huge -
# skipped automatically so a "index my whole C: drive" request doesn't
# spend hours crawling caches/build output.
_SKIP_DIR_NAMES = {
    "node_modules",
    "__pycache__",
    ".git",
    ".venv",
    "venv",
    "$RECYCLE.BIN",
    "System Volume Information",
}


class FileIndexer:
    """Build/search/maintain the local sqlite filename index."""

    def _conn(self) -> sqlite3.Connection:
        INDEX_DIR.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(INDEX_DB))
        conn.execute(
            "CREATE TABLE IF NOT EXISTS files ("
            " path TEXT PRIMARY KEY, name TEXT, ext TEXT, root TEXT,"
            " size INTEGER, mtime REAL)"
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_name ON files(name)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_root ON files(root)")
        conn.execute(
            "CREATE TABLE IF NOT EXISTS index_meta (" " root TEXT PRIMARY KEY, last_built REAL, file_count INTEGER)"
        )
        return conn

    def build_index(self, root: str, extensions: Optional[List[str]] = None, confirm: bool = False) -> Dict:
        """Walk `root` and (re)index every file under it, replacing any
        rows previously indexed for this same root. Optionally restrict
        to a list of extensions (e.g. ["pdf", "docx"]). Confirm-gated -
        can be a slow, disk-heavy operation on large roots."""
        p = Path(root)
        if not p.exists() or not p.is_dir():
            return {"error": f"Not a directory: {root}"}
        exts = {e.lower().lstrip(".") for e in extensions} if extensions else None
        if not confirm:
            return {
                "success": False,
                "needs_confirmation": True,
                "preview": f"Would crawl {p} and (re)build the file index for this root"
                f"{' (filtered to ' + ', '.join(sorted(exts)) + ')' if exts else ''}.",
                "message": "Call again with confirm=true to build.",
            }
        root_str = str(p.resolve())
        conn = self._conn()
        conn.execute("DELETE FROM files WHERE root = ?", (root_str,))
        count = 0
        for dirpath, dirnames, filenames in os.walk(root_str):
            dirnames[:] = [d for d in dirnames if d not in _SKIP_DIR_NAMES]
            for fname in filenames:
                ext = Path(fname).suffix.lstrip(".").lower()
                if exts and ext not in exts:
                    continue
                fpath = os.path.join(dirpath, fname)
                try:
                    st = os.stat(fpath)
                except OSError:
                    continue
                conn.execute(
                    "INSERT OR REPLACE INTO files (path, name, ext, root, size, mtime) " "VALUES (?, ?, ?, ?, ?, ?)",
                    (fpath, fname, ext, root_str, st.st_size, st.st_mtime),
                )
                count += 1
        conn.execute(
            "INSERT OR REPLACE INTO index_meta (root, last_built, file_count) VALUES (?, ?, ?)",
            (root_str, time.time(), count),
        )
        conn.commit()
        conn.close()
        return {"success": True, "root": root_str, "files_indexed": count}

    def search_index(self, query: str, extension: Optional[str] = None, limit: int = 50) -> Dict:
        """Search the index by filename substring (case-insensitive), most
        recently modified first."""
        if not query:
            return {"error": "query must be non-empty"}
        conn = self._conn()
        sql = "SELECT path, name, ext, size, mtime FROM files WHERE name LIKE ?"
        params = [f"%{query}%"]
        if extension:
            sql += " AND ext = ?"
            params.append(extension.lower().lstrip("."))
        sql += " ORDER BY mtime DESC LIMIT ?"
        params.append(max(1, min(limit, 500)))
        rows = conn.execute(sql, params).fetchall()
        conn.close()
        return {
            "success": True,
            "query": query,
            "count": len(rows),
            "results": [{"path": r[0], "name": r[1], "ext": r[2], "size": r[3], "mtime": r[4]} for r in rows],
        }

    def get_index_stats(self) -> Dict:
        """Total indexed files and per-root build info."""
        if not INDEX_DB.exists():
            return {"success": True, "total_files": 0, "roots": []}
        conn = self._conn()
        total = conn.execute("SELECT COUNT(*) FROM files").fetchone()[0]
        roots = conn.execute("SELECT root, last_built, file_count FROM index_meta ORDER BY last_built DESC").fetchall()
        conn.close()
        return {
            "success": True,
            "total_files": total,
            "roots": [{"root": r[0], "last_built": r[1], "file_count": r[2]} for r in roots],
        }

    def remove_root(self, root: str, confirm: bool = False) -> Dict:
        """Drop all indexed rows for one root (does not touch actual files
        on disk - only the index entry). Confirm-gated."""
        root_str = str(Path(root).resolve())
        if not confirm:
            return {
                "success": False,
                "needs_confirmation": True,
                "preview": f"Would remove {root_str} from the file index.",
                "message": "Call again with confirm=true to remove.",
            }
        conn = self._conn()
        cur = conn.execute("DELETE FROM files WHERE root = ?", (root_str,))
        conn.execute("DELETE FROM index_meta WHERE root = ?", (root_str,))
        conn.commit()
        removed = cur.rowcount
        conn.close()
        return {"success": True, "root": root_str, "rows_removed": removed}

    def clear_index(self, confirm: bool = False) -> Dict:
        """Wipe the entire index (every root). Confirm-gated."""
        if not confirm:
            return {
                "success": False,
                "needs_confirmation": True,
                "preview": "Would clear the entire file index (all indexed roots).",
                "message": "Call again with confirm=true to clear.",
            }
        conn = self._conn()
        conn.execute("DELETE FROM files")
        conn.execute("DELETE FROM index_meta")
        conn.commit()
        conn.close()
        return {"success": True, "cleared": True}
