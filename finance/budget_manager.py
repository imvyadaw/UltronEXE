"""Budget manager
=================
Per-category monthly budgets, checked against expense_tracker.py's
current-month totals. Same JSON-state persistence pattern as the rest of
finance/.
"""

import json
from pathlib import Path
from typing import Dict, Optional

from core.logger import get_logger
from finance.expense_tracker import get_expense_tracker

logger = get_logger("ultron.finance.budget")

DATA_PATH = Path(__file__).resolve().parents[1] / "storage" / "finance" / "budgets.json"

NEAR_LIMIT_RATIO = 0.8  # warn at 80% of budget, same shape as other threshold-based alerts in the project


class BudgetManager:
    def __init__(self):
        self._budgets: Dict[str, float] = self._load()

    def _load(self) -> Dict[str, float]:
        try:
            if DATA_PATH.exists():
                return json.loads(DATA_PATH.read_text(encoding="utf-8"))
        except Exception:
            logger.exception("budget_manager: state load failed, starting fresh")
        return {}

    def _save(self) -> None:
        try:
            DATA_PATH.parent.mkdir(parents=True, exist_ok=True)
            DATA_PATH.write_text(json.dumps(self._budgets, indent=2), encoding="utf-8")
        except Exception:
            logger.exception("budget_manager: state save failed")

    def set_budget(self, category: str, monthly_limit: float) -> Dict:
        category = (category or "").strip().lower()
        if not category:
            return {"success": False, "error": "category required"}
        try:
            monthly_limit = float(monthly_limit)
        except (TypeError, ValueError):
            return {"success": False, "error": f"invalid monthly_limit: {monthly_limit!r}"}
        if monthly_limit <= 0:
            return {"success": False, "error": "monthly_limit must be positive"}

        self._budgets[category] = round(monthly_limit, 2)
        self._save()
        return {"success": True, "category": category, "monthly_limit": self._budgets[category]}

    def remove_budget(self, category: str) -> Dict:
        category = (category or "").strip().lower()
        removed = self._budgets.pop(category, None) is not None
        if removed:
            self._save()
        return {"success": removed}

    def get_status(self) -> Dict:
        """Compares this-month spend (via expense_tracker.summary) against
        every set budget. Categories with no budget set are omitted -
        this reports on tracked budgets only, not every spending category."""
        spend = get_expense_tracker().summary(period="month")
        by_category = spend.get("by_category", {})

        rows = []
        alerts = []
        for category, limit in self._budgets.items():
            spent = by_category.get(category, 0.0)
            ratio = (spent / limit) if limit else 0.0
            status = "ok"
            if ratio >= 1.0:
                status = "over_budget"
            elif ratio >= NEAR_LIMIT_RATIO:
                status = "near_limit"
            row = {
                "category": category,
                "monthly_limit": limit,
                "spent_this_month": round(spent, 2),
                "remaining": round(limit - spent, 2),
                "percent_used": round(ratio * 100, 1),
                "status": status,
            }
            rows.append(row)
            if status != "ok":
                alerts.append(row)

        return {
            "success": True,
            "budgets": rows,
            "alerts": alerts,
            "has_alerts": bool(alerts),
        }


_budget_manager: Optional[BudgetManager] = None


def get_budget_manager() -> BudgetManager:
    global _budget_manager
    if _budget_manager is None:
        _budget_manager = BudgetManager()
    return _budget_manager
