"""Review queue
============
Where anything safety/policy.py classifies TIER_REVIEW waits for a
human decision instead of being silently skipped or silently allowed -
skill_learner.py's promote_masters() is the only caller today
(kind="skill_promotion"), but the shape is generic (`name`, `kind`,
`payload`) so a future risky auto-action elsewhere in the project can
reuse the same queue rather than growing its own.

Plain JSON file (storage/safety/review_queue.json), same storage
trade-off as learning/failure_learner.py's lessons file and
learning/forgetting.py's prune log: a personal assistant will see at
most a handful of items a week, and a flat file is easy to read by
hand without a query tool.

request_approval() is idempotent per (name, kind) while a matching item
is still pending, so a caller can call it every cycle (as
skill_learner.py's promote_masters() does) without piling up duplicate
requests for the same not-yet-decided item. approve()/reject() are a
human's decision; nothing in this module ever flips status on its own.
approved_unapplied()/mark_applied() let a caller (again, skill_learner.py)
come back later, find approvals it hasn't acted on yet, and mark them
done once it has - decoupling "a human said yes" from "the promotion
actually happened" so a caller crashing between the two doesn't lose
or replay the approval.
"""

import json
import time
from typing import Dict, List, Optional

from config import STORAGE_DIR
from core.logger import get_logger

logger = get_logger("safety.review_queue")

QUEUE_PATH = STORAGE_DIR / "safety" / "review_queue.json"

STATUS_PENDING = "pending"
STATUS_APPROVED = "approved"
STATUS_REJECTED = "rejected"


class ReviewQueue:
    """Holds procedures/skills that safety/policy.py flagged needs_review, until a human approves or rejects them."""

    def __init__(self):
        self._items: List[Dict] = self._load()

    def request_approval(
        self,
        name: str,
        kind: str,
        reason: str = "",
        matched: Optional[List[str]] = None,
        payload: Optional[Dict] = None,
    ) -> Dict:
        try:
            existing = self._find_pending(name, kind)
            if existing:
                return {"success": True, "id": existing["id"], "status": STATUS_PENDING, "already_queued": True}
            item = {
                "id": max((i["id"] for i in self._items), default=0) + 1,
                "name": name,
                "kind": kind,
                "reason": reason,
                "matched": matched or [],
                "payload": payload or {},
                "status": STATUS_PENDING,
                "applied": False,
                "requested_at": time.time(),
                "decided_at": None,
                "applied_at": None,
            }
            self._items.append(item)
            self._save()
            logger.info(f"Queued for review: {kind} '{name}' ({', '.join(matched or []) or reason})")
            return {"success": True, "id": item["id"], "status": STATUS_PENDING, "already_queued": False}
        except Exception as e:
            logger.error(f"request_approval() failed: {e}")
            return {"error": str(e)}

    def approve(self, item_id: int) -> Dict:
        return self._decide(item_id, STATUS_APPROVED)

    def reject(self, item_id: int) -> Dict:
        return self._decide(item_id, STATUS_REJECTED)

    def pending(self, kind: Optional[str] = None) -> Dict:
        items = [i for i in self._items if i["status"] == STATUS_PENDING and (kind is None or i["kind"] == kind)]
        return {"count": len(items), "items": items}

    def approved_unapplied(self, kind: Optional[str] = None) -> Dict:
        """Approved items a caller hasn't finished acting on yet - see
        module docstring for why this is split from approve()."""
        items = [
            i
            for i in self._items
            if i["status"] == STATUS_APPROVED and not i.get("applied") and (kind is None or i["kind"] == kind)
        ]
        return {"count": len(items), "items": items}

    def mark_applied(self, item_id: int) -> Dict:
        item = self._find(item_id)
        if item is None:
            return {"error": f"No review item with id {item_id}"}
        item["applied"] = True
        item["applied_at"] = time.time()
        self._save()
        return {"success": True, "item": item}

    def get(self, item_id: int) -> Dict:
        item = self._find(item_id)
        return item if item is not None else {"error": f"No review item with id {item_id}"}

    def history(self, limit: int = 20) -> Dict:
        entries = self._items[-limit:][::-1]
        return {"count": len(entries), "entries": entries}

    def _decide(self, item_id: int, status: str) -> Dict:
        try:
            item = self._find(item_id)
            if item is None:
                return {"error": f"No review item with id {item_id}"}
            if item["status"] != STATUS_PENDING:
                return {"error": f"Item {item_id} already {item['status']}"}
            item["status"] = status
            item["decided_at"] = time.time()
            self._save()
            logger.info(f"Review item {item_id} ('{item['name']}') -> {status}")
            return {"success": True, "item": item}
        except Exception as e:
            logger.error(f"_decide() failed: {e}")
            return {"error": str(e)}

    def _find(self, item_id: int) -> Optional[Dict]:
        return next((i for i in self._items if i["id"] == item_id), None)

    def _find_pending(self, name: str, kind: str) -> Optional[Dict]:
        return next(
            (i for i in self._items if i["name"] == name and i["kind"] == kind and i["status"] == STATUS_PENDING), None
        )

    # -- persistence -----------------------------------------------------
    def _load(self) -> List[Dict]:
        if not QUEUE_PATH.exists():
            return []
        try:
            return json.loads(QUEUE_PATH.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as e:
            logger.warning(f"Could not load review queue ({e}), starting fresh")
            return []

    def _save(self) -> None:
        QUEUE_PATH.parent.mkdir(parents=True, exist_ok=True)
        QUEUE_PATH.write_text(json.dumps(self._items, indent=2, ensure_ascii=False), encoding="utf-8")


_review_queue: Optional[ReviewQueue] = None


def get_review_queue() -> ReviewQueue:
    global _review_queue
    if _review_queue is None:
        _review_queue = ReviewQueue()
    return _review_queue
