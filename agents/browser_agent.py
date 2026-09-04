"""
Browser agent
=============
Thin wrapper over all three supported browser controllers plus the
cross-browser automation facade, for direct browser control without
going through the LLM tool-calling loop.
"""

from browser.chrome.chrome import ChromeController
from browser.edge.edge import EdgeController
from browser.firefox.firefox import FirefoxController
from browser.automation.automation import BrowserAutomation
from browser.cookies.cookies import CookieTools
from browser.downloads.downloads import DownloadsTools
from agents.base_agent import BaseAgent


class BrowserAgent(BaseAgent):
    capabilities = ["browser", "web", "chrome", "edge", "firefox"]

    def __init__(self):
        super().__init__("browser", "Chrome/Edge/Firefox control and cross-browser automation")
        self.chrome = ChromeController()
        self.edge = EdgeController()
        self.firefox = FirefoxController()
        self.automation = BrowserAutomation()
        self.cookies = CookieTools()
        self.downloads = DownloadsTools()

    def open(self, url: str):
        return self.chrome.open_url(url)

    def scroll(self, direction: str = "down", amount: int = 300):
        """Scroll whichever supported browser is currently active."""
        return self.automation.browser_scroll(direction, amount)
