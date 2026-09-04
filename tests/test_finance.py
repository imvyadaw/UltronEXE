import os
import tempfile
from pathlib import Path

import finance.expense_tracker as expense_mod
import finance.budget_manager as budget_mod


def _fresh_tracker(tmp_path):
    expense_mod.DATA_PATH = Path(tmp_path) / "expenses.json"
    return expense_mod.ExpenseTracker()


def _fresh_budget(tmp_path):
    budget_mod.DATA_PATH = Path(tmp_path) / "budgets.json"
    return budget_mod.BudgetManager()


def test_add_and_summarize_expense(tmp_path):
    tracker = _fresh_tracker(tmp_path)
    result = tracker.add_expense(500, "food", "zomato order")
    assert result["success"]
    assert result["entry"]["category"] == "food"

    summary = tracker.summary(period="month")
    assert summary["total_spent"] == 500
    assert summary["by_category"]["food"] == 500
    assert summary["top_category"] == "food"


def test_add_expense_auto_categorizes(tmp_path):
    tracker = _fresh_tracker(tmp_path)
    result = tracker.add_expense(200, note="uber ride to office")
    assert result["entry"]["category"] == "transport"


def test_add_expense_rejects_bad_amount(tmp_path):
    tracker = _fresh_tracker(tmp_path)
    assert tracker.add_expense(-50, "food")["success"] is False
    assert tracker.add_expense("not-a-number", "food")["success"] is False


def test_budget_status_flags_over_and_near_limit(tmp_path):
    # Wire the budget manager to a tracker that already has spend logged.
    tracker = _fresh_tracker(tmp_path)
    tracker.add_expense(950, "food", "big grocery run")
    budget_mod.get_expense_tracker = lambda: tracker

    budgets = _fresh_budget(tmp_path)
    budgets.set_budget("food", 1000)
    budgets.set_budget("transport", 500)

    status = budgets.get_status()
    assert status["has_alerts"] is True
    food_row = next(r for r in status["budgets"] if r["category"] == "food")
    assert food_row["status"] == "near_limit"  # 950/1000 = 95%

    transport_row = next(r for r in status["budgets"] if r["category"] == "transport")
    assert transport_row["status"] == "ok"


def test_market_watcher_price_extraction():
    from finance.market_watcher import _extract_price

    assert _extract_price("AAPL is trading at $189.32 today") == 189.32
    assert _extract_price("Bitcoin price: ₹5,432,100 right now") == 5432100.0
    assert _extract_price("no price mentioned here") is None
