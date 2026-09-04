"""Finance insights engine
===========================
Combines expense_tracker + budget_manager + market_watcher into one
report. If an ai_router is available, asks it for a short natural-
language narration of the numbers (same "inject a real AIRouter,
lazy-imported to dodge a circular import" pattern used by
intelligence/ultron_advanced/autonomous_learning.py's run_once()). If no
router is available (or the call fails), returns the raw numeric report
only - never blocks on the LLM being reachable, same fail-closed shape
as everything else in this project.
"""

from typing import Dict, Optional

from core.logger import get_logger
from finance.expense_tracker import get_expense_tracker
from finance.budget_manager import get_budget_manager
from finance.market_watcher import get_market_watcher

logger = get_logger("ultron.finance.insights")


class InsightsEngine:
    def generate_report(self, period: str = "month", narrate: bool = True) -> Dict:
        expense_summary = get_expense_tracker().summary(period=period)
        budget_status = get_budget_manager().get_status()
        watchlist = get_market_watcher().status().get("watchlist", {})

        report: Dict = {
            "success": True,
            "period": period,
            "expenses": expense_summary,
            "budgets": budget_status,
            "watchlist_snapshot": watchlist,
        }

        if narrate:
            narration = self._narrate(report)
            if narration:
                report["narration"] = narration

        return report

    def _narrate(self, report: Dict) -> Optional[str]:
        try:
            from ai.ai_router import AIRouter

            router = AIRouter()
            prompt = (
                "Summarize this personal finance snapshot in 3-4 short sentences, plain language, "
                "point out anything concerning (over-budget categories, big spend jumps) and one "
                "practical suggestion. Data:\n"
                f"{report['expenses']}\n{report['budgets']}\n"
            )
            text = router.complete(prompt)
            return (text or "").strip() or None
        except Exception:
            logger.info("finance.insights_engine: narration unavailable (no ai_router or call failed), returning raw numbers only")
            return None


_insights_engine: Optional[InsightsEngine] = None


def get_insights_engine() -> InsightsEngine:
    global _insights_engine
    if _insights_engine is None:
        _insights_engine = InsightsEngine()
    return _insights_engine
