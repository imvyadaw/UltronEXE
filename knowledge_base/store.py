"""Knowledge store
================
Generic JSON-file-per-record storage for one knowledge_base/ category
(facts/, concepts/, sources/, relationships/). Each record is a single
JSON file named "<id>.json" inside the category directory, so the
knowledge base stays human-browsable on disk (open knowledge_base/facts/
and read a fact) instead of being locked inside a binary DB file the
way memory/long_term's SQLite store is.

Kept deliberately dumb: no schema enforcement beyond "it's a dict with
an id", no locking (personal-assistant scale - hundreds to low
thousands of records per category, single process). The meaning of
each category (facts vs concepts vs sources vs relationships, and how
they link to each other) lives one layer up, in
knowledge_base/__init__.py.
"""

import json
import time
import uuid
from pathlib import Path
from typing import Dict, List, Optional

CATEGORY_ROOT = Path(__file__).resolve().parent


class RecordStore:
    """CRUD over one JSON-file-per-record folder under knowledge_base/."""

    def __init__(self, category: str):
        self.category = category
        self.dir = CATEGORY_ROOT / category
        self.dir.mkdir(parents=True, exist_ok=True)

    def _path(self, record_id: str) -> Path:
        return self.dir / f"{record_id}.json"

    def add(self, data: Dict, record_id: Optional[str] = None) -> Dict:
        """Create a new record. Generates a short random id if none given."""
        try:
            record_id = record_id or uuid.uuid4().hex[:12]
            now = time.time()
            record = {**data, "id": record_id, "created_at": now, "updated_at": now}
            self._path(record_id).write_text(json.dumps(record, indent=2, ensure_ascii=False), encoding="utf-8")
            return record
        except Exception as e:
            return {"error": str(e)}

    def get(self, record_id: str) -> Optional[Dict]:
        path = self._path(record_id)
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return None

    def update(self, record_id: str, **fields) -> Dict:
        record = self.get(record_id)
        if record is None:
            return {"error": f"No {self.category} record with id {record_id}"}
        record.update(fields)
        record["id"] = record_id
        record["updated_at"] = time.time()
        try:
            self._path(record_id).write_text(json.dumps(record, indent=2, ensure_ascii=False), encoding="utf-8")
            return record
        except Exception as e:
            return {"error": str(e)}

    def delete(self, record_id: str) -> Dict:
        path = self._path(record_id)
        if not path.exists():
            return {"error": f"No {self.category} record with id {record_id}"}
        path.unlink()
        return {"success": True, "deleted_id": record_id}

    def list_all(self) -> List[Dict]:
        records = []
        for path in sorted(self.dir.glob("*.json")):
            try:
                records.append(json.loads(path.read_text(encoding="utf-8")))
            except Exception:
                continue
        return records

    def find(self, **filters) -> List[Dict]:
        """Return records where every key in `filters` matches exactly.
        Filters set to None are ignored, so callers can pass optional
        lookup keys (e.g. url=None) without special-casing them."""
        active = {k: v for k, v in filters.items() if v is not None}
        if not active:
            return []
        return [r for r in self.list_all() if all(r.get(k) == v for k, v in active.items())]

    def search_text(self, query: str, fields: List[str]) -> List[Dict]:
        """Case-insensitive substring search over the given string fields."""
        q = query.lower().strip()
        if not q:
            return []
        return [r for r in self.list_all() if any(q in str(r.get(f, "")).lower() for f in fields)]

    def count(self) -> int:
        return len(list(self.dir.glob("*.json")))
