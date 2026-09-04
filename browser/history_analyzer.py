"""Browsing history analyzer
=========================
Reads Chrome/Edge's History SQLite file (same locked-file-copy trick
as browser/downloads/downloads.py's get_download_history) and computes
summary stats: most-visited sites, visits by hour/weekday, and a
plain recent-history listing - things a single raw query wouldn't give
directly.
"""

import os
import shutil
import sqlite3
import tempfile
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List
from urllib.parse import urlparse

CHROME_HISTORY_PATH = Path.home() / "AppData/Local/Google/Chrome/User Data/Default/History"
EDGE_HISTORY_PATH = Path.home() / "AppData/Local/Microsoft/Edge/User Data/Default/History"

# Chrome/Edge store visit_count timestamps as microseconds since 1601-01-01 (Windows epoch).
_WINDOWS_EPOCH = datetime(1601, 1, 1)


def _chrome_time_to_datetime(chrome_time: int) -> datetime:
    return _WINDOWS_EPOCH + timedelta(microseconds=chrome_time)


class HistoryAnalyzer:
    """Read-only analysis of Chrome/Edge browsing history."""

    def _history_path(self, browser: str) -> Path:
        return CHROME_HISTORY_PATH if browser.lower() == "chrome" else EDGE_HISTORY_PATH

    def _query(self, browser: str, sql: str, params: tuple = ()) -> List[tuple]:
        path = self._history_path(browser)
        if not path.exists():
            raise FileNotFoundError(f"{browser} history file not found at {path}")
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
            tmp_path = tmp.name
        shutil.copy2(path, tmp_path)
        try:
            conn = sqlite3.connect(tmp_path)
            cur = conn.cursor()
            cur.execute(sql, params)
            rows = cur.fetchall()
            conn.close()
            return rows
        finally:
            os.unlink(tmp_path)

    def recent_history(self, browser: str = "chrome", limit: int = 30) -> Dict:
        """Most recently visited URLs, most recent first."""
        try:
            rows = self._query(
                browser,
                "SELECT title, url, last_visit_time, visit_count FROM urls ORDER BY last_visit_time DESC LIMIT ?",
                (limit,),
            )
            entries = [
                {
                    "title": r[0],
                    "url": r[1],
                    "last_visited": _chrome_time_to_datetime(r[2]).isoformat() if r[2] else None,
                    "visit_count": r[3],
                }
                for r in rows
            ]
            return {"browser": browser, "count": len(entries), "history": entries}
        except Exception as e:
            return {"error": str(e)}

    def most_visited(self, browser: str = "chrome", limit: int = 15) -> Dict:
        """Top sites by total visit count."""
        try:
            rows = self._query(
                browser, "SELECT title, url, visit_count FROM urls ORDER BY visit_count DESC LIMIT ?", (limit,)
            )
            entries = [{"title": r[0], "url": r[1], "visit_count": r[2]} for r in rows]
            return {"browser": browser, "count": len(entries), "most_visited": entries}
        except Exception as e:
            return {"error": str(e)}

    def top_domains(self, browser: str = "chrome", limit: int = 15, days: int = 30) -> Dict:
        """Top domains visited in the last `days` days, by number of visits."""
        try:
            cutoff = datetime.now() - timedelta(days=days)
            cutoff_chrome = int((cutoff - _WINDOWS_EPOCH).total_seconds() * 1_000_000)
            rows = self._query(
                browser,
                "SELECT url FROM visits JOIN urls ON visits.url = urls.id WHERE visit_time > ?",
                (cutoff_chrome,),
            )
            domains = Counter()
            for (url,) in rows:
                try:
                    domain = urlparse(url).netloc
                    if domain:
                        domains[domain] += 1
                except Exception:
                    continue
            top = domains.most_common(limit)
            return {"browser": browser, "days": days, "top_domains": [{"domain": d, "visits": c} for d, c in top]}
        except Exception as e:
            return {"error": str(e)}

    def activity_by_hour(self, browser: str = "chrome", days: int = 30) -> Dict:
        """Visit counts bucketed by hour of day (0-23), over the last `days` days -
        useful for spotting browsing habit patterns."""
        try:
            cutoff = datetime.now() - timedelta(days=days)
            cutoff_chrome = int((cutoff - _WINDOWS_EPOCH).total_seconds() * 1_000_000)
            rows = self._query(browser, "SELECT visit_time FROM visits WHERE visit_time > ?", (cutoff_chrome,))
            hours = Counter()
            for (vt,) in rows:
                try:
                    hours[_chrome_time_to_datetime(vt).hour] += 1
                except Exception:
                    continue
            distribution = [hours.get(h, 0) for h in range(24)]
            return {
                "browser": browser,
                "days": days,
                "visits_by_hour": distribution,
                "peak_hour": max(range(24), key=lambda h: hours.get(h, 0)) if hours else None,
            }
        except Exception as e:
            return {"error": str(e)}

    def search_history(self, query: str, browser: str = "chrome", limit: int = 30) -> Dict:
        """Search titles/URLs in history for a substring."""
        try:
            like = f"%{query}%"
            rows = self._query(
                browser,
                "SELECT title, url, last_visit_time FROM urls WHERE title LIKE ? OR url LIKE ? ORDER BY last_visit_time DESC LIMIT ?",
                (like, like, limit),
            )
            entries = [
                {
                    "title": r[0],
                    "url": r[1],
                    "last_visited": _chrome_time_to_datetime(r[2]).isoformat() if r[2] else None,
                }
                for r in rows
            ]
            return {"query": query, "browser": browser, "count": len(entries), "matches": entries}
        except Exception as e:
            return {"error": str(e)}
