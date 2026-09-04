"""VLC media player automation (playback via its own global hotkeys)."""

import time
from typing import Dict

from apps.base_app import BaseApp


class VLCApp(BaseApp):
    """Open media files and control playback in VLC."""

    APP_NAME = "vlc"
    PROCESS_NAMES = ["vlc.exe", "vlc"]
    EXE_HINTS = ["vlc", "vlc.exe"]

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

    def _hotkey(self, key: str) -> Dict:
        focused = self.focus()
        if focused.get("error"):
            return focused
        time.sleep(0.2)
        return self.press_key(key)

    def play_pause(self) -> Dict:
        return self._hotkey("space")

    def next_track(self) -> Dict:
        return self._hotkey("n")

    def previous_track(self) -> Dict:
        return self._hotkey("p")

    def volume_up(self) -> Dict:
        return self._hotkey("ctrl+up")

    def volume_down(self) -> Dict:
        return self._hotkey("ctrl+down")

    def fullscreen(self) -> Dict:
        return self._hotkey("f")
