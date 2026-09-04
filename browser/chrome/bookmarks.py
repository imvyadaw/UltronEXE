"""
Chrome bookmarks
==================
Chrome-scoped view over browser/bookmark_manager.py's BookmarkManager
(which already handles Chrome's JSON bookmarks format) - kept as a thin
wrapper rather than duplicating the JSON-tree walking logic, so there's
one place that actually parses the Bookmarks file.
"""

from typing import Dict

from browser.bookmark_manager import BookmarkManager


class ChromeBookmarks:
    """List/search/add/delete bookmarks in Chrome."""

    def __init__(self):
        self._manager = BookmarkManager()

    def list_bookmarks(self) -> Dict:
        return self._manager.list_bookmarks(browser="chrome")

    def search_bookmarks(self, query: str) -> Dict:
        return self._manager.search_bookmarks(query, browser="chrome")

    def add_bookmark(self, name: str, url: str, folder: str = "Bookmarks bar") -> Dict:
        """Close Chrome first - it rewrites the Bookmarks file from memory
        on exit, which would overwrite this otherwise."""
        return self._manager.add_bookmark(name, url, browser="chrome", folder=folder)

    def delete_bookmark(self, name: str) -> Dict:
        return self._manager.delete_bookmark(name, browser="chrome")
