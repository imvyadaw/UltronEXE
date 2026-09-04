"""
Notion integration
==================
Create/read/update pages and query databases via the official Notion API
(raw requests). Setup (.env): NOTION_API_KEY (Notion -> My Integrations ->
create an internal integration, then share the target page/database with it).
"""

import os
from typing import Any, Dict, List, Optional

import requests

BASE_URL = "https://api.notion.com/v1"
NOTION_VERSION = "2022-06-28"


class NotionClient:
    """Wrapper around the Notion API."""

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("NOTION_API_KEY")

    def is_configured(self) -> bool:
        return bool(self.api_key)

    def _headers(self) -> Dict:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Notion-Version": NOTION_VERSION,
        }

    def _check(self) -> Optional[Dict]:
        if not self.is_configured():
            return {"success": False, "error": "NOTION_API_KEY not set in .env"}
        return None

    def create_page(self, parent_id: str, title: str, content: str = "", is_database: bool = False) -> Dict:
        """parent_id: a database_id (if is_database=True) or a page_id."""
        err = self._check()
        if err:
            return err
        try:
            parent = {"database_id": parent_id} if is_database else {"page_id": parent_id}
            title_key = "Name" if is_database else "title"
            properties = {title_key: {"title": [{"text": {"content": title}}]}}

            children = []
            if content:
                children.append(
                    {
                        "object": "block",
                        "type": "paragraph",
                        "paragraph": {"rich_text": [{"type": "text", "text": {"content": content}}]},
                    }
                )

            payload = {"parent": parent, "properties": properties, "children": children}
            resp = requests.post(f"{BASE_URL}/pages", headers=self._headers(), json=payload, timeout=15)
            resp.raise_for_status()
            data = resp.json()
            return {"success": True, "page_id": data["id"], "url": data.get("url")}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_page(self, page_id: str) -> Dict:
        err = self._check()
        if err:
            return err
        try:
            resp = requests.get(f"{BASE_URL}/pages/{page_id}", headers=self._headers(), timeout=15)
            resp.raise_for_status()
            return {"success": True, "page": resp.json()}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def append_text(self, page_id: str, text: str) -> Dict:
        """Append a paragraph block to an existing page."""
        err = self._check()
        if err:
            return err
        try:
            payload = {
                "children": [
                    {
                        "object": "block",
                        "type": "paragraph",
                        "paragraph": {"rich_text": [{"type": "text", "text": {"content": text}}]},
                    }
                ]
            }
            resp = requests.patch(
                f"{BASE_URL}/blocks/{page_id}/children", headers=self._headers(), json=payload, timeout=15
            )
            resp.raise_for_status()
            return {"success": True, "page_id": page_id}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def query_database(
        self,
        database_id: str,
        filter_obj: Optional[Dict] = None,
        sorts: Optional[List[Dict]] = None,
        page_size: int = 20,
    ) -> Dict:
        err = self._check()
        if err:
            return err
        try:
            payload: Dict[str, Any] = {"page_size": page_size}
            if filter_obj:
                payload["filter"] = filter_obj
            if sorts:
                payload["sorts"] = sorts
            resp = requests.post(
                f"{BASE_URL}/databases/{database_id}/query", headers=self._headers(), json=payload, timeout=15
            )
            resp.raise_for_status()
            results = resp.json().get("results", [])
            return {"success": True, "count": len(results), "results": results}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def search(self, query: str, filter_type: Optional[str] = None) -> Dict:
        """filter_type: 'page' or 'database', or None for both."""
        err = self._check()
        if err:
            return err
        try:
            payload: Dict[str, Any] = {"query": query}
            if filter_type:
                payload["filter"] = {"value": filter_type, "property": "object"}
            resp = requests.post(f"{BASE_URL}/search", headers=self._headers(), json=payload, timeout=15)
            resp.raise_for_status()
            results = resp.json().get("results", [])
            return {"success": True, "count": len(results), "results": results}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def update_page_properties(self, page_id: str, properties: Dict) -> Dict:
        err = self._check()
        if err:
            return err
        try:
            resp = requests.patch(
                f"{BASE_URL}/pages/{page_id}", headers=self._headers(), json={"properties": properties}, timeout=15
            )
            resp.raise_for_status()
            return {"success": True, "page_id": page_id}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def archive_page(self, page_id: str) -> Dict:
        err = self._check()
        if err:
            return err
        try:
            resp = requests.patch(
                f"{BASE_URL}/pages/{page_id}", headers=self._headers(), json={"archived": True}, timeout=15
            )
            resp.raise_for_status()
            return {"success": True, "page_id": page_id, "action": "archived"}
        except Exception as e:
            return {"success": False, "error": str(e)}
