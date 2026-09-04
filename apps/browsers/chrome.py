"""
Google Chrome automation
=========================
URL/tab/window/incognito control by resolving the real chrome.exe (via
the App Paths registry or PATH) and passing it command-line flags -
AppManager.open_application()'s os.startfile() alone can't pass args.
"""

import subprocess
import time
from typing import Dict, Optional
from urllib.parse import quote

from apps.base_app import BaseApp


class ChromeApp(BaseApp):
    """Open URLs, tabs, windows, and incognito sessions in Chrome."""

    APP_NAME = "chrome"
    PROCESS_NAMES = ["chrome.exe", "chrome"]
    EXE_HINTS = ["chrome", "google-chrome", "chrome.exe"]

    def open_url(self, url: str, incognito: bool = False, new_window: bool = False) -> Dict:
        try:
            exe = self.resolve_executable()
            flags = []
            if incognito:
                flags.append("--incognito")
            if new_window:
                flags.append("--new-window")
            if exe:
                subprocess.Popen([exe, *flags, url])
                return {"success": True, "url": url, "incognito": incognito, "new_window": new_window}
            import webbrowser

            webbrowser.open(url, new=2 if new_window else 0)
            return {"success": True, "url": url, "note": "opened via default browser handler - chrome.exe not found"}
        except Exception as e:
            return {"error": str(e)}

    def new_tab(self, url: Optional[str] = None) -> Dict:
        """Open url (or a blank tab) in the already-running Chrome window."""
        return self.open_url(url or "chrome://newtab", incognito=False, new_window=False)

    def new_window(self, url: Optional[str] = None) -> Dict:
        return self.open_url(url or "chrome://newtab", new_window=True)

    def open_incognito(self, url: Optional[str] = None) -> Dict:
        return self.open_url(url or "about:blank", incognito=True, new_window=True)

    def search(self, query: str) -> Dict:
        return self.open_url(f"https://www.google.com/search?q={quote(query)}")

    def close_tab(self) -> Dict:
        """Close the current tab (requires Chrome to be the focused window)."""
        focused = self.focus()
        if focused.get("error"):
            return focused
        time.sleep(0.3)
        return self.press_key("ctrl+w")

    def close_all(self) -> Dict:
        return self.close()

    def bookmark_current_page(self) -> Dict:
        """Ctrl+D on whatever tab is currently focused in Chrome."""
        focused = self.focus()
        if focused.get("error"):
            return focused
        time.sleep(0.3)
        return self.press_key("ctrl+d")
