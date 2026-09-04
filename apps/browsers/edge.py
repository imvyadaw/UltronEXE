"""Microsoft Edge automation (Chromium-based, same flag surface as Chrome
minus the flag name: --inprivate instead of --incognito)."""

import subprocess
import time
from typing import Dict, Optional
from urllib.parse import quote

from apps.base_app import BaseApp


class EdgeApp(BaseApp):
    """Open URLs, tabs, windows, and InPrivate sessions in Edge."""

    APP_NAME = "edge"
    PROCESS_NAMES = ["msedge.exe", "msedge"]
    EXE_HINTS = ["msedge", "msedge.exe"]

    def open_url(self, url: str, private: bool = False, new_window: bool = False) -> Dict:
        try:
            exe = self.resolve_executable()
            flags = []
            if private:
                flags.append("--inprivate")
            if new_window:
                flags.append("--new-window")
            if exe:
                subprocess.Popen([exe, *flags, url])
                return {"success": True, "url": url, "private": private, "new_window": new_window}
            import webbrowser

            webbrowser.open(url, new=2 if new_window else 0)
            return {"success": True, "url": url, "note": "opened via default browser handler - msedge.exe not found"}
        except Exception as e:
            return {"error": str(e)}

    def new_tab(self, url: Optional[str] = None) -> Dict:
        return self.open_url(url or "edge://newtab")

    def new_window(self, url: Optional[str] = None) -> Dict:
        return self.open_url(url or "edge://newtab", new_window=True)

    def open_inprivate(self, url: Optional[str] = None) -> Dict:
        return self.open_url(url or "about:blank", private=True, new_window=True)

    def search(self, query: str) -> Dict:
        return self.open_url(f"https://www.bing.com/search?q={quote(query)}")

    def close_tab(self) -> Dict:
        focused = self.focus()
        if focused.get("error"):
            return focused
        time.sleep(0.3)
        return self.press_key("ctrl+w")

    def close_all(self) -> Dict:
        return self.close()
