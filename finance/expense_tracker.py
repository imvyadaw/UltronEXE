"""Expense tracker
==================
Local, JSON-backed expense log. Same persistence shape as
intelligence/ultron_advanced/autonomous_learning.py's STATE_PATH pattern
(no new DB engine needed for something this small - a list of dicts is
plenty, and it stays human-readable/editable).

Not a bank integration - the user (or a voice command like "500 rupees
kharch hue khane pe") tells Ultron what was spent; Ultron just tracks,
categorizes, and summarizes it.
"""

import json
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

from core.logger import get_logger

logger = get_logger("ultron.finance.expenses")

DATA_PATH = Path(__file__).resolve().parents[1] / "storage" / "finance" / "expenses.json"

# Best-effort auto-category keyword map - used only when the caller
# doesn't supply an explicit category. Intentionally small and editable;
# unmatched text falls back to "other" rather than guessing wrong.
_AUTO_CATEGORY_KEYWORDS = {
    "food": ["restaurant", "zomato", "swiggy", "khana", "food", "cafe", "coffee", "grocery", "groceries"],
    "transport": ["uber", "ola", "petrol", "diesel", "fuel", "cab", "auto", "metro", "bus", "train"],
    "bills": ["electricity", "bill", "recharge", "internet", "wifi", "rent", "emi"],
    "shopping": ["amazon", "flipkart", "myntra", "shopping", "clothes"],
    "entertainment": ["movie", "netflix", "spotify", "game", "party"],
    "health": ["medicine", "doctor", "hospital", "pharmacy", "medical"],
    "education": ["course", "book", "tuition", "fees", "college"],
}


def _guess_category(note: str) -> str:
    text = (note or "").lower()
    for category, keywords in _AUTO_CATEGORY_KEYWORDS.items():
        if any(k in text for k in keywords):
            return category
    return "other"


class ExpenseTracker:
    """Add, list, and summarize expenses. All amounts are plain floats in
    whatever single currency the user is using consistently - Ultron
    doesn't do currency conversion here."""

    def __init__(self):
        self._entries: List[Dict] = self._load()

    # -- persistence ------------------------------------------------
    def _load(self) -> List[Dict]:
        try:
            if DATA_PATH.exists():
                return json.loads(DATA_PATH.read_text(encoding="utf-8"))
        except Exception:
            logger.exception("expense_tracker: state load failed, starting fresh")
        return []

    def _save(self) -> None:
        try:
            DATA_PATH.parent.mkdir(parents=True, exist_ok=True)
            DATA_PATH.write_text(json.dumps(self._entries, indent=2), encoding="utf-8")
        except Exception:
            logger.exception("expense_tracker: state save failed")

    # -- writes -------------------------------------------------------
    def add_expense(self, amount: float, category: Optional[str] = None, note: str = "") -> Dict:
        try:
            amount = float(amount)
        except (TypeError, ValueError):
            return {"success": False, "error": f"invalid amount: {amount!r}"}
        if amount <= 0:
            return {"success": False, "error": "amount must be positive"}

        entry = {
            "id": uuid.uuid4().hex[:8],
            "amount": round(amount, 2),
            "category": (category or _guess_category(note)).strip().lower(),
            "note": note or "",
            "timestamp": time.time(),
            "date": datetime.now(timezone.utc).astimezone().date().isoformat(),
        }
        self._entries.append(entry)
        self._save()
        logger.info(f"expense_tracker: logged {entry['amount']} in '{entry['category']}' ({entry['note']!r})")
        return {"success": True, "entry": entry}

    # -- reads ----------------------------------------------------------
    def list_expenses(
        self,
        category: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        limit: int = 50,
    ) -> Dict:
        results = self._entries
        if category:
            category = category.strip().lower()
            results = [e for e in results if e["category"] == category]
        if start_date:
            results = [e for e in results if e["date"] >= start_date]
        if end_date:
            results = [e for e in results if e["date"] <= end_date]
        results = sorted(results, key=lambda e: e["timestamp"], reverse=True)[:limit]
        return {"success": True, "count": len(results), "entries": results}

    def summary(self, period: str = "month") -> Dict:
        """period: 'month' (calendar month so far) or 'all'."""
        now = datetime.now(timezone.utc).astimezone()
        entries = self._entries
        if period == "month":
            prefix = now.strftime("%Y-%m")
            entries = [e for e in entries if e["date"].startswith(prefix)]

        by_category: Dict[str, float] = {}
        total = 0.0
        for e in entries:
            by_category[e["category"]] = round(by_category.get(e["category"], 0.0) + e["amount"], 2)
            total += e["amount"]

        top_category = max(by_category, key=by_category.get) if by_category else None
        return {
            "success": True,
            "period": period,
            "total_spent": round(total, 2),
            "entry_count": len(entries),
            "by_category": by_category,
            "top_category": top_category,
        }


_expense_tracker: Optional[ExpenseTracker] = None


def get_expense_tracker() -> ExpenseTracker:
    global _expense_tracker
    if _expense_tracker is None:
        _expense_tracker = ExpenseTracker()
    return _expense_tracker
