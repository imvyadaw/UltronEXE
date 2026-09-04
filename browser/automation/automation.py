"""Cross-browser automation facade
=================================
Generic browser control that auto-detects which supported browser
(Chrome, Edge, or Firefox) currently has a window open/focused, and
routes the action to the matching controller. Lets the AI call one
"browser_scroll" / "browser_navigate" tool without needing to know or
ask which browser the user is actually using.
"""

from typing import Dict

from browser.chrome.chrome import ChromeController
from browser.edge.edge import EdgeController
from browser.firefox.firefox import FirefoxController

try:
    import pygetwindow as gw

    HAS_PYGETWINDOW = True
except ImportError:
    HAS_PYGETWINDOW = False


class BrowserAutomation:
    """Detects the active/open browser and delegates to its controller."""

    def __init__(self):
        self.chrome = ChromeController()
        self.edge = EdgeController()
        self.firefox = FirefoxController()

    def detect_active_browser(self) -> str:
        """Return 'chrome', 'edge', or 'firefox' based on open windows
        (prefers the currently active/foreground window if it's a browser)."""
        if not HAS_PYGETWINDOW:
            return "chrome"  # sensible default when we can't inspect windows
        try:
            active = gw.getActiveWindow()
            if active:
                title = active.title
                if "Edge" in title:
                    return "edge"
                if "Firefox" in title:
                    return "firefox"
                if "Chrome" in title or "Google Chrome" in title:
                    return "chrome"
            # fall back to whichever is open at all
            all_titles = " ".join(w.title for w in gw.getAllWindows())
            if "Edge" in all_titles:
                return "edge"
            if "Firefox" in all_titles:
                return "firefox"
            return "chrome"
        except Exception:
            return "chrome"

    def _controller_for(self, browser: str = None):
        browser = (browser or self.detect_active_browser()).lower()
        return {"chrome": self.chrome, "edge": self.edge, "firefox": self.firefox}.get(browser, self.chrome), browser

    def browser_scroll(self, direction: str = "down", amount: int = 300, browser: str = None) -> Dict:
        """Scroll the page in whichever supported browser is active (or the named one)."""
        controller, name = self._controller_for(browser)
        method = getattr(controller, f"scroll_{name}")
        return method(direction, amount)

    def browser_navigate(self, action: str, browser: str = None) -> Dict:
        """Navigate (back/forward/refresh/URL) in whichever supported browser is active."""
        controller, name = self._controller_for(browser)
        method = getattr(controller, f"{name}_navigate")
        return method(action)

    def browser_type(self, text: str, browser: str = None) -> Dict:
        """Type text into the focused element in whichever supported browser is active."""
        controller, name = self._controller_for(browser)
        method = getattr(controller, f"type_in_{name}")
        return method(text)

    def browser_zoom(self, action: str, browser: str = None) -> Dict:
        """Zoom in/out/reset in whichever supported browser is active."""
        controller, name = self._controller_for(browser)
        method = getattr(controller, f"{name}_zoom")
        return method(action)

    def list_tabs(self, browser: str = None) -> Dict:
        """List open tabs in whichever supported browser is active (or the named one)."""
        controller, name = self._controller_for(browser)
        method = getattr(controller, f"list_{name}_tabs")
        return method()

    def close_tab(self, tab_identifier: str, browser: str = None) -> Dict:
        """Close a tab by title match in whichever supported browser is active."""
        controller, name = self._controller_for(browser)
        method = getattr(controller, f"close_{name}_tab")
        return method(tab_identifier)
