"""Cross-browser tab manager
=========================
Unifies tab listing/closing across Chrome, Edge, and Firefox by
composing the three existing per-browser controllers
(browser/chrome/chrome.py, browser/edge/edge.py,
browser/firefox/firefox.py) instead of duplicating their UI-Automation
logic, so callers can ask "what tabs are open" / "close this tab"
without caring which browser it's actually in.
"""

from typing import Dict

from browser.chrome.chrome import ChromeController
from browser.edge.edge import EdgeController
from browser.firefox.firefox import FirefoxController


class TabManager:
    """List/close/switch tabs across whichever supported browsers are open."""

    def __init__(self):
        self._chrome = ChromeController()
        self._edge = EdgeController()
        self._firefox = FirefoxController()

    def list_all_tabs(self) -> Dict:
        """List tabs from every browser that's currently open, tagged by browser."""
        results = {}
        for name, controller, method in [
            ("chrome", self._chrome, "list_chrome_tabs"),
            ("edge", self._edge, "list_edge_tabs"),
            ("firefox", self._firefox, "list_firefox_tabs"),
        ]:
            try:
                results[name] = getattr(controller, method)()
            except Exception as e:
                results[name] = {"error": str(e)}
        total = sum(len(r.get("tabs", [])) for r in results.values() if isinstance(r, dict) and "tabs" in r)
        return {"by_browser": results, "total_tabs": total}

    def close_tab(self, tab: str, browser: str = "chrome") -> Dict:
        """Close a tab (by title/index match, same as the per-browser controllers)
        in the given browser."""
        browser = browser.lower()
        if browser == "chrome":
            return self._chrome.close_chrome_tab(tab)
        if browser == "edge":
            return self._edge.close_edge_tab(tab)
        if browser == "firefox":
            return self._firefox.close_firefox_tab(tab)
        return {"error": f"Unknown browser '{browser}' - use chrome, edge, or firefox"}

    def close_tabs_matching(self, query: str) -> Dict:
        """Close every tab across all browsers whose title contains `query`."""
        listing = self.list_all_tabs()
        results = []
        for browser, data in listing["by_browser"].items():
            for tab in data.get("tabs", []) if isinstance(data, dict) else []:
                title = tab.get("title", "") if isinstance(tab, dict) else str(tab)
                if query.lower() in title.lower():
                    results.append({"browser": browser, "title": title, "result": self.close_tab(title, browser)})
        return {"query": query, "closed_count": len(results), "results": results}

    def count_tabs(self) -> Dict:
        """Quick tab-count summary per browser."""
        listing = self.list_all_tabs()
        return {
            browser: len(data.get("tabs", [])) if isinstance(data, dict) else 0
            for browser, data in listing["by_browser"].items()
        }
