"""Financial Intelligence module
=================================
New capability (not present in either MJ or the pre-upgrade ULTRON tree):
personal expense tracking, category budgets with over/near-limit alerts,
and a recurring stock/crypto price watcher built on the same
scheduler + JSON-state pattern as
intelligence/ultron_advanced/autonomous_learning.py.

Sub-modules:
    expense_tracker.py  - log/list/summarize expenses (JSON-backed).
    budget_manager.py   - per-category monthly budgets vs actual spend.
    market_watcher.py   - recurring price checks for watched symbols,
                           threshold alerts, start/stop/status/history
                           shaped exactly like AutonomousLearningScheduler.
    insights_engine.py  - combines the three into one human-readable
                           report, optionally narrated by the AI router.

Everything here is read-only / local-state-only: no payments, no bank
connections, no money actually moves. Expense entries are user-supplied
numbers; market prices are best-effort (parsed from search results, not
a licensed market-data feed) and explicitly labelled as such.
"""
