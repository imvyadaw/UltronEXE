"""iTunes / Apple Music (Windows) automation."""

from typing import Dict

from apps.base_app import BaseApp

try:
    import pyautogui

    HAS_PYAUTOGUI = True
except ImportError:
    HAS_PYAUTOGUI = False


class ITunesApp(BaseApp):
    """Open iTunes and control playback via system media keys."""

    APP_NAME = "itunes"
    PROCESS_NAMES = ["itunes.exe", "itunes"]
    EXE_HINTS = ["itunes", "itunes.exe"]

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

    def play_file(self, path: str) -> Dict:
        exe = self.resolve_executable()
        if exe:
            return self.run_command([exe, path])
        try:
            import os

            os.startfile(path)
            return {"success": True, "path": path}
        except Exception as e:
            return {"error": str(e)}
