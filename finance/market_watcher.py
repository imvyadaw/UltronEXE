"""Market watcher
=================
Recurring stock/crypto price checks for a user-maintained watchlist, with
optional above/below alert thresholds. Built on
automation/scheduler/task_scheduler.py, same start/stop/status/history
shape and JSON-state persistence pattern as
intelligence/ultron_advanced/autonomous_learning.py's
AutonomousLearningScheduler - deliberately mirrored so this feature is
familiar to anyone who already knows how the internet-learning scheduler
works.

Price source: skills/internet/web_tools.py's search_internet() (same
Wikipedia -> Google CSE -> DuckDuckGo fallback chain used everywhere else
in the project), best-effort-parsed for a currency figure in the result
snippets. This is NOT a licensed market-data feed - no real-time
exchange API key is wired in, so figures can lag or occasionally fail to
parse. Every result is labelled "best_effort" so a caller (or the user)
never mistakes this for a trading-grade price.

Safety: read-only. No orders are placed, no trading action exists
anywhere in this module - it only reads a price and, optionally, logs an
alert when a threshold is crossed. Off by default
(ULTRON_MARKET_WATCH_ENABLED), same opt-in convention as
ULTRON_LEARN_FROM_INTERNET. Halts the recurring schedule after
MAX_CONSECUTIVE_FAILURES, same self-protecting behavior as the learning
scheduler, so a dead network doesn't spin forever unnoticed.
"""

import json
import re
import time
from pathlib import Path
from typing import Dict, List, Optional

from core.logger import get_logger
from automation.scheduler.task_scheduler import get_scheduler

logger = get_logger("ultron.finance.market_watcher")

DEFAULT_INTERVAL_SECONDS = 30 * 60  # 30 min - prices move faster than the 6h learning cadence
MAX_HISTORY = 20
MAX_CONSECUTIVE_FAILURES = 3

STATE_PATH = Path(__file__).resolve().parents[1] / "storage" / "finance" / "market_watch_state.json"

_PRICE_PATTERN = re.compile(r"[\$₹€£]\s?([0-9][0-9,]*\.?[0-9]*)")


def _extract_price(text: str) -> Optional[float]:
    """Best-effort: first currency-prefixed number in the text."""
    match = _PRICE_PATTERN.search(text or "")
    if not match:
        return None
    try:
        return float(match.group(1).replace(",", ""))
    except ValueError:
        return None


class MarketWatcher:
    """Runs a price-lookup search for each watched symbol on a recurring
    interval, checks it against any alert_above/alert_below thresholds,
    and keeps a rolling history."""

    def __init__(self):
        self._backend = get_scheduler()
        self._task_id: Optional[str] = None
        self._history: List[Dict] = []
        self._consecutive_failures = 0
        self._state = self._load_state()

    # -- state (watchlist) ---------------------------------------------
    def _load_state(self) -> Dict:
        try:
            if STATE_PATH.exists():
                loaded = json.loads(STATE_PATH.read_text(encoding="utf-8"))
                loaded.setdefault("symbols", {})
                return loaded
        except Exception:
            logger.exception("market_watcher: state load failed, starting fresh")
        return {"symbols": {}}

    def _save_state(self) -> None:
        try:
            STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
            STATE_PATH.write_text(json.dumps(self._state, indent=2), encoding="utf-8")
        except Exception:
            logger.exception("market_watcher: state save failed")

    def add_symbol(
        self, symbol: str, alert_above: Optional[float] = None, alert_below: Optional[float] = None
    ) -> Dict:
        symbol = (symbol or "").strip().upper()
        if not symbol:
            return {"success": False, "error": "symbol required"}
        self._state["symbols"][symbol] = {
            "alert_above": float(alert_above) if alert_above is not None else None,
            "alert_below": float(alert_below) if alert_below is not None else None,
            "last_price": None,
            "last_checked": None,
        }
        self._save_state()
        return {"success": True, "symbol": symbol, "watchlist": list(self._state["symbols"].keys())}

    def remove_symbol(self, symbol: str) -> Dict:
        symbol = (symbol or "").strip().upper()
        removed = self._state["symbols"].pop(symbol, None) is not None
        if removed:
            self._save_state()
        return {"success": removed, "watchlist": list(self._state["symbols"].keys())}

    # -- price lookup -----------------------------------------------------
    def _lookup_price(self, symbol: str) -> Dict:
        from skills.internet.web_tools import WebTools

        result = WebTools().search_internet(f"{symbol} price today", num_results=3)
        if not result.get("success"):
            return {"success": False, "error": result.get("error", "search failed")}

        for item in result.get("results", []):
            price = _extract_price(item.get("description", "")) or _extract_price(item.get("title", ""))
            if price is not None:
                return {"success": True, "price": price, "source_url": item.get("url"), "confidence": "best_effort"}

        return {"success": False, "error": f"could not parse a price for {symbol} from search results"}

    # -- cycle --------------------------------------------------------------
    def check_now(self, symbol: Optional[str] = None) -> Dict:
        """Check one symbol (or every watched symbol if none given).
        Safe to call directly for an on-demand 'abhi price check karo'."""
        symbols = [symbol.strip().upper()] if symbol else list(self._state["symbols"].keys())
        if not symbols:
            return {"success": False, "error": "watchlist is empty - add a symbol first"}

        started = time.time()
        checked = []
        any_alert = False
        for sym in symbols:
            entry = self._state["symbols"].setdefault(
                sym, {"alert_above": None, "alert_below": None, "last_price": None, "last_checked": None}
            )
            lookup = self._lookup_price(sym)
            row = {"symbol": sym, "success": lookup.get("success", False)}
            if lookup.get("success"):
                price = lookup["price"]
                row["price"] = price
                row["source_url"] = lookup.get("source_url")
                row["confidence"] = lookup.get("confidence")
                entry["last_price"] = price
                entry["last_checked"] = time.time()

                alert = None
                if entry.get("alert_above") is not None and price >= entry["alert_above"]:
                    alert = f"{sym} at {price} is at/above your alert_above threshold {entry['alert_above']}"
                elif entry.get("alert_below") is not None and price <= entry["alert_below"]:
                    alert = f"{sym} at {price} is at/below your alert_below threshold {entry['alert_below']}"
                if alert:
                    row["alert"] = alert
                    any_alert = True
                    logger.warning(f"market_watcher: {alert}")
            else:
                row["error"] = lookup.get("error")
            checked.append(row)

        self._save_state()
        result = {
            "success": True,
            "checked": checked,
            "any_alert": any_alert,
            "started_at": started,
            "duration_seconds": round(time.time() - started, 3),
        }

        if any(r["success"] for r in checked):
            self._consecutive_failures = 0
        else:
            self._consecutive_failures += 1
            if self._consecutive_failures >= MAX_CONSECUTIVE_FAILURES and self._task_id is not None:
                logger.warning(
                    f"market_watcher: {self._consecutive_failures} consecutive failed cycles - "
                    "pausing the recurring schedule until a human calls start() again."
                )
                self.stop()

        self._history.append(result)
        self._history = self._history[-MAX_HISTORY:]
        return result

    def start(self, interval_seconds: float = DEFAULT_INTERVAL_SECONDS) -> Dict:
        if self._task_id is not None:
            return {"error": "Market watcher already running", "task_id": self._task_id}
        self._task_id = self._backend.run_every(interval_seconds, self.check_now)
        self._consecutive_failures = 0
        logger.info(f"market_watcher started, interval={interval_seconds}s")
        return {"success": True, "task_id": self._task_id, "interval_seconds": interval_seconds}

    def stop(self) -> Dict:
        if self._task_id is None:
            return {"error": "Market watcher is not running"}
        cancelled = self._backend.cancel(self._task_id)
        self._task_id = None
        return {"success": cancelled}

    def status(self) -> Dict:
        return {
            "running": self._task_id is not None,
            "task_id": self._task_id,
            "watchlist": self._state.get("symbols", {}),
            "consecutive_failures": self._consecutive_failures,
            "cycles_run": len(self._history),
            "last_cycle": self._history[-1] if self._history else None,
        }

    def history(self, limit: int = MAX_HISTORY) -> Dict:
        entries = self._history[-limit:][::-1]
        return {"count": len(entries), "entries": entries}


_market_watcher: Optional[MarketWatcher] = None


def get_market_watcher() -> MarketWatcher:
    global _market_watcher
    if _market_watcher is None:
        _market_watcher = MarketWatcher()
    return _market_watcher
