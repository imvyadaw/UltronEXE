"""Financial intelligence tool wiring
======================================
Exposes finance/ (expense_tracker, budget_manager, market_watcher,
insights_engine) as tools, wired the same lazy-handler-dict way as
ai/autonomous_learning_tools.py.

Market watcher's ULTRON_MARKET_WATCH_ENABLED env flag only controls
whether the recurring scheduler auto-starts at boot (see
core/assistant.py) - these tools work either way, so "is stock ko track
karo" / "abhi price check karo" works in-session without a restart, same
pattern as autolearn_start/autolearn_now.
"""

from typing import Dict


def _tool(name: str, description: str, properties: dict = None, required: list = None) -> dict:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": properties or {},
                "required": required or [],
            },
        },
    }


def _get_expenses():
    from finance.expense_tracker import get_expense_tracker

    return get_expense_tracker()


def _get_budgets():
    from finance.budget_manager import get_budget_manager

    return get_budget_manager()


def _get_watcher():
    from finance.market_watcher import get_market_watcher

    return get_market_watcher()


def _get_insights():
    from finance.insights_engine import get_insights_engine

    return get_insights_engine()


FINANCE_TOOLS = [
    _tool(
        "expense_add",
        "Log a personal expense. Call whenever the user mentions spending money "
        "(e.g. '500 rupees khana pe kharch hue', 'I spent $40 on Uber').",
        {
            "amount": {"type": "number", "description": "Amount spent (positive number)."},
            "category": {
                "type": "string",
                "description": "Spending category (e.g. food, transport, bills, shopping). "
                "Optional - auto-guessed from the note if omitted.",
            },
            "note": {"type": "string", "description": "Short description of the expense."},
        },
        ["amount"],
    ),
    _tool(
        "expense_list",
        "List recent logged expenses, optionally filtered by category.",
        {
            "category": {"type": "string", "description": "Filter by category. Optional."},
            "limit": {"type": "integer", "description": "Max entries to return. Defaults to 50."},
        },
    ),
    _tool(
        "expense_summary",
        "Get total spend and a per-category breakdown for this month (or all-time).",
        {"period": {"type": "string", "description": "'month' (default, calendar month so far) or 'all'."}},
    ),
    _tool(
        "budget_set",
        "Set (or update) a monthly spending limit for a category. Call when the user says "
        "something like 'food pe max 5000 rupay mahine ka budget rakho'.",
        {
            "category": {"type": "string", "description": "Category to budget."},
            "monthly_limit": {"type": "number", "description": "Monthly limit amount."},
        },
        ["category", "monthly_limit"],
    ),
    _tool(
        "budget_status",
        "Check every set budget against this month's actual spend, and flag any category that "
        "is near or over its limit. Call when the user asks 'am I over budget' / 'budget kaisa chal raha hai'.",
    ),
    _tool(
        "market_watch_add",
        "Add a stock or crypto symbol to the price watchlist, with optional above/below alert "
        "thresholds. Call when the user asks to track/watch a symbol's price.",
        {
            "symbol": {"type": "string", "description": "Ticker/symbol, e.g. AAPL, BTC."},
            "alert_above": {"type": "number", "description": "Alert if price reaches/exceeds this. Optional."},
            "alert_below": {"type": "number", "description": "Alert if price drops to/below this. Optional."},
        },
        ["symbol"],
    ),
    _tool(
        "market_watch_remove",
        "Remove a symbol from the price watchlist.",
        {"symbol": {"type": "string", "description": "Ticker/symbol to remove."}},
        ["symbol"],
    ),
    _tool(
        "market_watch_status",
        "Check the price watcher: whether the recurring scheduler is running, current watchlist, "
        "last known prices, and the last check cycle's result.",
    ),
    _tool(
        "market_check_now",
        "Immediately look up the current (best-effort, search-derived) price for one symbol, or "
        "every watched symbol if none given, without waiting for the next scheduled cycle.",
        {"symbol": {"type": "string", "description": "Specific symbol to check now. Optional."}},
    ),
    _tool(
        "finance_insights",
        "Generate a combined finance report (spend summary + budget alerts + watchlist snapshot), "
        "with a short plain-language narration when possible. Call for 'meri financial summary do' "
        "/ 'is mahine ka kharcha kaisa raha' style requests.",
        {"period": {"type": "string", "description": "'month' (default) or 'all'."}},
    ),
]

FINANCE_DIRECT_HANDLERS: Dict = {
    "expense_add": lambda a: _get_expenses().add_expense(
        a.get("amount"), a.get("category"), a.get("note", "")
    ),
    "expense_list": lambda a: _get_expenses().list_expenses(
        a.get("category"), limit=int(a.get("limit", 50))
    ),
    "expense_summary": lambda a: _get_expenses().summary(a.get("period", "month")),
    "budget_set": lambda a: _get_budgets().set_budget(a.get("category", ""), a.get("monthly_limit")),
    "budget_status": lambda a: _get_budgets().get_status(),
    "market_watch_add": lambda a: _get_watcher().add_symbol(
        a.get("symbol", ""), a.get("alert_above"), a.get("alert_below")
    ),
    "market_watch_remove": lambda a: _get_watcher().remove_symbol(a.get("symbol", "")),
    "market_watch_status": lambda a: _get_watcher().status(),
    "market_check_now": lambda a: _get_watcher().check_now(a.get("symbol") or None),
    "finance_insights": lambda a: _get_insights().generate_report(a.get("period", "month")),
}
