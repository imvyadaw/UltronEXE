"""Firefox automation: window/tab control (firefox.py) plus download history (downloads.py)."""

from browser.firefox.firefox import FirefoxController
from browser.firefox.downloads import FirefoxDownloads

__all__ = ["FirefoxController", "FirefoxDownloads"]
