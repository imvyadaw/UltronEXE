"""Mozilla Firefox automation."""

import subprocess
import time
from typing import Dict, Optional
from urllib.parse import quote

from apps.base_app import BaseApp


class FirefoxApp(BaseApp):
    """Open URLs, tabs, windows, and private windows in Firefox."""

    APP_NAME = "firefox"
    PROCESS_NAMES = ["firefox.exe", "firefox"]
    EXE_HINTS = ["firefox", "firefox.exe"]

    def open_url(self, url: str, private: bool = False, new_window: bool = False) -> Dict:
        try:
            exe = self.resolve_executable()
            flags = []
            if private:
                flags.append("-private-window")
            elif new_window:
                flags.append("-new-window")
            else:
                flags.append("-new-tab")
            if exe:
                subprocess.Popen([exe, *flags, url])
                return {"success": True, "url": url, "private": private, "new_window": new_window}
            import webbrowser

            webbrowser.open(url, new=2 if new_window else 0)
            return {"success": True, "url": url, "note": "opened via default browser handler - firefox.exe not found"}
        except Exception as e:
            return {"error": str(e)}

    def new_tab(self, url: Optional[str] = None) -> Dict:
        return self.open_url(url or "about:blank")

    def new_window(self, url: Optional[str] = None) -> Dict:
        return self.open_url(url or "about:blank", new_window=True)

    def open_private_window(self, url: Optional[str] = None) -> Dict:
        return self.open_url(url or "about:blank", private=True)

    def search(self, query: str) -> Dict:
        return self.open_url(f"https://duckduckgo.com/?q={quote(query)}")

    def close_tab(self) -> Dict:
        focused = self.focus()
        if focused.get("error"):
            return focused
        time.sleep(0.3)
        return self.press_key("ctrl+w")

    def close_all(self) -> Dict:
        return self.close()
