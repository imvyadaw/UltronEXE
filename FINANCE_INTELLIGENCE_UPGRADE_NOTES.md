# Financial Intelligence upgrade

## Added
- `finance/expense_tracker.py` - log/list/summarize personal expenses,
  JSON-backed, with best-effort keyword auto-categorization when no
  category is given.
- `finance/budget_manager.py` - per-category monthly budgets, checked
  against expense_tracker's this-month totals; flags `near_limit` (>=80%)
  and `over_budget` (>=100%).
- `finance/market_watcher.py` - recurring stock/crypto price checks for a
  user watchlist, with optional `alert_above`/`alert_below` thresholds.
  Same scheduler + JSON-state + start/stop/status/history shape as
  `intelligence/ultron_advanced/autonomous_learning.py`'s
  `AutonomousLearningScheduler`, deliberately mirrored for consistency.
  Price source is `skills/internet/web_tools.py`'s existing search
  fallback chain, regex-parsed for a currency figure - not a licensed
  market-data feed, always labelled `confidence: "best_effort"`.
- `finance/insights_engine.py` - combines all three into one report;
  narrates it in plain language via `ai/ai_router.py` when available,
  falls back to raw numbers only if the router isn't reachable.
- `ai/finance_tools.py` - 10 new tools: `expense_add`, `expense_list`,
  `expense_summary`, `budget_set`, `budget_status`, `market_watch_add`,
  `market_watch_remove`, `market_watch_status`, `market_check_now`,
  `finance_insights`.
- `tests/test_finance.py` - expense add/summarize/auto-category/
  validation, budget over/near-limit flagging, market price-regex
  extraction.

## Wired
- `ai/tools_schema.py` - `TOOLS = TOOLS + FINANCE_TOOLS`.
- `ai/tool_runtime.py` - `_DIRECT_HANDLERS.update(FINANCE_DIRECT_HANDLERS)`.
- `core/assistant.py` - market watcher auto-starts at boot only if
  `ULTRON_MARKET_WATCH_ENABLED=true` (off by default). Expense tracking
  and budgets have no background component and need no gate - the tools
  just work.
- `.env.example` - added `ULTRON_MARKET_WATCH_ENABLED` and
  `ULTRON_MARKET_WATCH_INTERVAL_MINUTES` (default 30) next to the
  existing `ULTRON_LEARN_FROM_INTERNET` block.

## Why this and not something else
Audited both MJ_FINAL_FIXED and the pre-upgrade ULTRON tree for a
missing capability rather than duplicating something that already
existed (e.g. deep-research tooling already exists in
`skills/web/research.py` / `ai/new_skills_tools.py`'s `deep_research` /
`multi_agent_swarm/specialist_agents/research_agent.py` - adding another
research module would have been a rename, not a new capability). Grepped
for `financ*`, `budget*`, `stock*`, `crypto*`, `portfolio*`, `expense*`
across the whole tree - zero matches. Personal finance tracking is a
core "personal assistant" capability that was genuinely absent.

## Safety
- No payments, no bank/brokerage connections, no trading action anywhere
  in this module - purely local state (expenses/budgets are
  user-supplied numbers) and read-only price lookups.
- Market watcher: off by default, self-halts after 3 consecutive failed
  cycles (same protection as `autonomous_learning.py`), and every price
  is labelled `best_effort` so it's never mistaken for a trading-grade
  feed.
- No new unrestricted execution path; nothing here touches
  `core/permissions.py`, `approval/`, or `safety/`.

## Not done (be aware)
- No currency conversion - all amounts are assumed to be one consistent
  currency the user is using.
- Price parsing is regex-over-search-snippets; a real market-data API
  key (not currently in `.env.example`) would make `market_watcher.py`
  meaningfully more accurate if one gets added later.
- `insights_engine.py`'s narration call has no retry/self-consistency -
  unlike `intelligence/deliberative_reasoning.py`, this is a single
  `ai_router.complete()` call. Fine for a summary paragraph; wiring it
  through the deliberative reasoner would be the natural next step if
  narration quality ever matters more than it does today.
