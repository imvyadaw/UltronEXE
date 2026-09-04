"""Opera Browser automation (Chromium-based)."""

import subprocess
from typing import Dict, Optional
from urllib.parse import quote

from apps.base_app import BaseApp


class OperaApp(BaseApp):
    """Open URLs, tabs, windows, and private windows in Opera."""

    APP_NAME = "opera"
    PROCESS_NAMES = ["opera.exe", "opera"]
    EXE_HINTS = ["opera", "opera.exe"]

    def open_url(self, url: str, private: bool = False, new_window: bool = False) -> Dict:
        try:
            exe = self.resolve_executable()
            flags = []
            if private:
                flags.append("--private")
            if new_window or private:
                flags.append("--new-window")
            if exe:
                subprocess.Popen([exe, *flags, url])
                return {"success": True, "url": url, "private": private}
            import webbrowser

            webbrowser.open(url, new=2 if new_window else 0)
            return {"success": True, "url": url, "note": "opened via default browser handler - opera.exe not found"}
        except Exception as e:
            return {"error": str(e)}

    def new_tab(self, url: Optional[str] = None) -> Dict:
        return self.open_url(url or "opera://newtab")

    def new_window(self, url: Optional[str] = None) -> Dict:
        return self.open_url(url or "opera://newtab", new_window=True)

    def open_private_window(self, url: Optional[str] = None) -> Dict:
        return self.open_url(url or "about:blank", private=True)

    def search(self, query: str) -> Dict:
        return self.open_url(f"https://www.google.com/search?q={quote(query)}")

    def close_all(self) -> Dict:
        return self.close()
