"""
Chrome history
================
Chrome-scoped view over browser/history_analyzer.py's HistoryAnalyzer
(recent/most-visited/top-domains/hourly-pattern queries), plus
delete_url() which the analyzer doesn't have - a write against Chrome's
own History SQLite file, so Chrome needs to be closed first (the file
is locked while it's running).
"""

import sqlite3
from pathlib import Path
from typing import Dict

from browser.history_analyzer import HistoryAnalyzer

CHROME_HISTORY_PATH = Path.home() / "AppData/Local/Google/Chrome/User Data/Default/History"


class ChromeHistory:
    """Read Chrome browsing history, and delete individual URLs from it."""

    def __init__(self):
        self._analyzer = HistoryAnalyzer()

    def recent_history(self, limit: int = 30) -> Dict:
        return self._analyzer.recent_history(browser="chrome", limit=limit)

    def most_visited(self, limit: int = 15) -> Dict:
        return self._analyzer.most_visited(browser="chrome", limit=limit)

    def top_domains(self, limit: int = 15, days: int = 30) -> Dict:
        return self._analyzer.top_domains(browser="chrome", limit=limit, days=days)

    def activity_by_hour(self, days: int = 30) -> Dict:
        return self._analyzer.activity_by_hour(browser="chrome", days=days)

    def search_history(self, query: str, limit: int = 30) -> Dict:
        return self._analyzer.search_history(query, browser="chrome", limit=limit)

    def delete_url(self, url: str, confirm: bool = False) -> Dict:
        """Delete every visit entry for one URL from Chrome's history.
        Close Chrome first. Safety-gated: needs confirm=true."""
        if not confirm:
            return {"error": "This permanently deletes the URL from history. Call again with confirm=true to proceed."}
        if not CHROME_HISTORY_PATH.exists():
            return {"error": f"Chrome history file not found at {CHROME_HISTORY_PATH}"}
        try:
            conn = sqlite3.connect(str(CHROME_HISTORY_PATH))
            cur = conn.cursor()
            cur.execute("SELECT id FROM urls WHERE url = ?", (url,))
            row = cur.fetchone()
            if not row:
                conn.close()
                return {"error": f"URL not found in history: {url}"}
            url_id = row[0]
            cur.execute("DELETE FROM visits WHERE url = ?", (url_id,))
            cur.execute("DELETE FROM urls WHERE id = ?", (url_id,))
            conn.commit()
            conn.close()
            return {"success": True, "deleted_url": url}
        except sqlite3.OperationalError as e:
            return {
                "error": f"{e} - Chrome likely needs to be closed first (the History file is locked while it's running)"
            }
        except Exception as e:
            return {"error": str(e)}
