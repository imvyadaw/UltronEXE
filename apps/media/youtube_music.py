"""YouTube Music automation (web app - no official desktop client/API,
so this drives the browser tab + system media keys)."""

import webbrowser
from typing import Dict
from urllib.parse import quote

from apps.base_app import BaseApp

try:
    import pyautogui

    HAS_PYAUTOGUI = True
except ImportError:
    HAS_PYAUTOGUI = False


class YouTubeMusicApp(BaseApp):
    """Open music.youtube.com and control playback via media keys."""

    APP_NAME = "youtube music"
    PROCESS_NAMES = []  # runs inside a browser tab, not its own process

    def open_web(self) -> Dict:
        try:
            webbrowser.open("https://music.youtube.com")
            return {"success": True}
        except Exception as e:
            return {"error": str(e)}

    def search_and_open(self, query: str) -> Dict:
        try:
            webbrowser.open(f"https://music.youtube.com/search?q={quote(query)}")
            return {"success": True, "query": query}
        except Exception as e:
            return {"error": str(e)}

    def _media_key(self, key: str) -> Dict:
        if not HAS_PYAUTOGUI:
            return {"error": "pyautogui not installed - run: pip install pyautogui"}
        try:
            pyautogui.press(key)
            return {"success": True, "key": key}
        except Exception as e:
            return {"error": str(e)}

    def play_pause(self) -> Dict:
        return self._media_key("playpause")

    def next_track(self) -> Dict:
        return self._media_key("nexttrack")

    def previous_track(self) -> Dict:
        return self._media_key("prevtrack")
