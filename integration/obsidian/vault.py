"""
Obsidian integration
====================
Obsidian has no cloud API - vaults are just folders of Markdown files on
disk, so this integration works directly with the filesystem (optionally
via the community "Local REST API" plugin for live-reload note creation
if the app is running). Covers: create/read/update notes, append to daily
notes, search vault, manage tags/links, list backlinks.

Setup (.env): OBSIDIAN_VAULT_PATH pointing at your vault's root folder.
Optional: OBSIDIAN_REST_API_KEY + OBSIDIAN_REST_API_URL if you have the
"Local REST API" community plugin installed (lets Ultron push updates
into an already-open Obsidian instance instantly).
"""

import os
import re
from datetime import date
from pathlib import Path
from typing import Dict, Optional

import requests


class ObsidianClient:
    """File-based Obsidian vault operations, with an optional REST API path."""

    def __init__(
        self, vault_path: Optional[str] = None, rest_api_url: Optional[str] = None, rest_api_key: Optional[str] = None
    ):
        vp = vault_path or os.getenv("OBSIDIAN_VAULT_PATH")
        self.vault_path = Path(vp).expanduser() if vp else None
        self.rest_api_url = rest_api_url or os.getenv("OBSIDIAN_REST_API_URL", "https://127.0.0.1:27124")
        self.rest_api_key = rest_api_key or os.getenv("OBSIDIAN_REST_API_KEY")

    def is_configured(self) -> bool:
        return bool(self.vault_path and self.vault_path.exists())

    def _resolve_note(self, note_path: str) -> Path:
        if not note_path.endswith(".md"):
            note_path += ".md"
        return self.vault_path / note_path

    # -- basic file ops ---------------------------------------------------
    def create_note(self, note_path: str, content: str = "", overwrite: bool = False) -> Dict:
        if not self.is_configured():
            return {"success": False, "error": "OBSIDIAN_VAULT_PATH not set or doesn't exist."}
        try:
            path = self._resolve_note(note_path)
            if path.exists() and not overwrite:
                return {"success": False, "error": f"Note already exists: {note_path} (pass overwrite=True to replace)"}
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
            return {"success": True, "path": str(path)}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def read_note(self, note_path: str) -> Dict:
        if not self.is_configured():
            return {"success": False, "error": "OBSIDIAN_VAULT_PATH not set."}
        try:
            path = self._resolve_note(note_path)
            if not path.exists():
                return {"success": False, "error": f"Note not found: {note_path}"}
            return {"success": True, "path": str(path), "content": path.read_text(encoding="utf-8")}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def append_note(self, note_path: str, text: str) -> Dict:
        if not self.is_configured():
            return {"success": False, "error": "OBSIDIAN_VAULT_PATH not set."}
        try:
            path = self._resolve_note(note_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as f:
                f.write(("\n" if path.exists() and path.stat().st_size > 0 else "") + text)
            return {"success": True, "path": str(path)}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def delete_note(self, note_path: str) -> Dict:
        if not self.is_configured():
            return {"success": False, "error": "OBSIDIAN_VAULT_PATH not set."}
        try:
            path = self._resolve_note(note_path)
            if not path.exists():
                return {"success": False, "error": f"Note not found: {note_path}"}
            path.unlink()
            return {"success": True, "path": str(path), "action": "deleted"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    # -- daily notes --------------------------------------------------------
    def append_to_daily_note(self, text: str, daily_folder: str = "Daily") -> Dict:
        today = date.today().isoformat()
        note_path = f"{daily_folder}/{today}"
        result = self.append_note(note_path, text)
        result["date"] = today
        return result

    # -- search / navigation -------------------------------------------------
    def search_vault(self, query: str, max_results: int = 20) -> Dict:
        if not self.is_configured():
            return {"success": False, "error": "OBSIDIAN_VAULT_PATH not set."}
        try:
            matches = []
            for md_file in self.vault_path.rglob("*.md"):
                try:
                    text = md_file.read_text(encoding="utf-8", errors="ignore")
                except Exception:
                    continue
                if query.lower() in text.lower():
                    idx = text.lower().find(query.lower())
                    snippet = text[max(0, idx - 40) : idx + 80].replace("\n", " ")
                    matches.append({"note": str(md_file.relative_to(self.vault_path)), "snippet": snippet})
                    if len(matches) >= max_results:
                        break
            return {"success": True, "query": query, "count": len(matches), "matches": matches}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def list_notes(self, folder: str = "") -> Dict:
        if not self.is_configured():
            return {"success": False, "error": "OBSIDIAN_VAULT_PATH not set."}
        try:
            base = self.vault_path / folder if folder else self.vault_path
            notes = [str(p.relative_to(self.vault_path)) for p in base.rglob("*.md")]
            return {"success": True, "count": len(notes), "notes": notes}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_backlinks(self, note_name: str) -> Dict:
        """Find every note containing a [[note_name]] wikilink."""
        if not self.is_configured():
            return {"success": False, "error": "OBSIDIAN_VAULT_PATH not set."}
        try:
            stem = note_name.replace(".md", "")
            pattern = re.compile(r"\[\[" + re.escape(stem) + r"(\|[^\]]*)?\]\]")
            backlinks = []
            for md_file in self.vault_path.rglob("*.md"):
                try:
                    text = md_file.read_text(encoding="utf-8", errors="ignore")
                except Exception:
                    continue
                if pattern.search(text):
                    backlinks.append(str(md_file.relative_to(self.vault_path)))
            return {"success": True, "note": stem, "count": len(backlinks), "backlinks": backlinks}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def add_tag(self, note_path: str, tag: str) -> Dict:
        """Append a #tag to the end of a note (doesn't touch frontmatter)."""
        if not tag.startswith("#"):
            tag = "#" + tag
        return self.append_note(note_path, f"\n{tag}")

    # -- optional live REST API (Local REST API community plugin) -----------
    def rest_api_available(self) -> bool:
        return bool(self.rest_api_key)

    def push_via_rest_api(self, note_path: str, content: str) -> Dict:
        """Write directly into a currently-open Obsidian instance (instant
        reload in the app) instead of writing to disk. Requires the
        'Local REST API' community plugin to be installed and running."""
        if not self.rest_api_key:
            return {
                "success": False,
                "error": "OBSIDIAN_REST_API_KEY not set - install the Local REST API plugin first.",
            }
        try:
            headers = {"Authorization": f"Bearer {self.rest_api_key}", "Content-Type": "text/markdown"}
            # The Obsidian Local REST API plugin serves a self-signed cert,
            # so TLS verification can't succeed against it - but only skip
            # verification when we're actually talking to loopback. If
            # OBSIDIAN_REST_API_URL has been pointed at a remote host,
            # verify=False there would silently accept a MITM'd connection.
            from urllib.parse import urlparse

            host = urlparse(self.rest_api_url).hostname or ""
            is_loopback = host in ("127.0.0.1", "localhost", "::1")
            resp = requests.put(
                f"{self.rest_api_url}/vault/{note_path}",
                headers=headers,
                data=content,
                timeout=10,
                verify=not is_loopback,
            )
            resp.raise_for_status()
            return {"success": True, "path": note_path}
        except Exception as e:
            return {"success": False, "error": str(e)}
