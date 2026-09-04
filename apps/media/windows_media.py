"""Windows Media Player / generic system media-session automation
(system media keys - works against whatever app currently owns the OS
media session, not just Windows Media Player specifically)."""

from typing import Dict

from apps.base_app import BaseApp

try:
    import pyautogui

    HAS_PYAUTOGUI = True
except ImportError:
    HAS_PYAUTOGUI = False


class WindowsMediaApp(BaseApp):
    """Open Windows Media Player and control system-wide media playback."""

    APP_NAME = "windows media player"
    PROCESS_NAMES = ["wmplayer.exe", "wmplayer"]
    EXE_HINTS = ["wmplayer", "wmplayer.exe"]

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

    def stop(self) -> Dict:
        return self._media_key("stop")

    def volume_up(self) -> Dict:
        return self._media_key("volumeup")

    def volume_down(self) -> Dict:
        return self._media_key("volumedown")

    def mute(self) -> Dict:
        return self._media_key("volumemute")

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
