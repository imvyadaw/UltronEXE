"""Brave Browser automation (Chromium-based)."""

import subprocess
from typing import Dict, Optional
from urllib.parse import quote

from apps.base_app import BaseApp


class BraveApp(BaseApp):
    """Open URLs, tabs, windows, and private (Tor) windows in Brave."""

    APP_NAME = "brave"
    PROCESS_NAMES = ["brave.exe", "brave"]
    EXE_HINTS = ["brave", "brave.exe"]

    def open_url(self, url: str, private: bool = False, tor: bool = False, new_window: bool = False) -> Dict:
        try:
            exe = self.resolve_executable()
            flags = []
            if tor:
                flags.append("--incognito")  # Brave routes Tor windows through a private window
                flags.append("--tor")
            elif private:
                flags.append("--incognito")
            if new_window or private or tor:
                flags.append("--new-window")
            if exe:
                subprocess.Popen([exe, *flags, url])
                return {"success": True, "url": url, "private": private, "tor": tor}
            import webbrowser

            webbrowser.open(url, new=2 if new_window else 0)
            return {"success": True, "url": url, "note": "opened via default browser handler - brave.exe not found"}
        except Exception as e:
            return {"error": str(e)}

    def new_tab(self, url: Optional[str] = None) -> Dict:
        return self.open_url(url or "brave://newtab")

    def new_window(self, url: Optional[str] = None) -> Dict:
        return self.open_url(url or "brave://newtab", new_window=True)

    def open_private_window(self, url: Optional[str] = None) -> Dict:
        return self.open_url(url or "about:blank", private=True)

    def open_tor_window(self, url: Optional[str] = None) -> Dict:
        return self.open_url(url or "about:blank", tor=True)

    def search(self, query: str) -> Dict:
        return self.open_url(f"https://search.brave.com/search?q={quote(query)}")

    def close_all(self) -> Dict:
        return self.close()
