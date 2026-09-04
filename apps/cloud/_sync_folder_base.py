"""Shared helper for cloud-sync-client apps: dropping a file into the
local sync folder is the most reliable "upload" there is (the desktop
client picks it up and syncs automatically), so every module here tries
to locate that folder under the user's home directory."""

import shutil
from pathlib import Path
from typing import Dict, List, Optional

from apps.base_app import BaseApp


class SyncFolderApp(BaseApp):
    """Base for cloud-storage apps whose desktop client keeps a local
    sync folder (Drive, OneDrive, Dropbox). Subclasses set
    SYNC_FOLDER_CANDIDATES with likely folder names under the home dir."""

    SYNC_FOLDER_CANDIDATES: List[str] = []
    WEB_URL: str = ""

    def find_sync_folder(self) -> Optional[Path]:
        home = Path.home()
        for candidate in self.SYNC_FOLDER_CANDIDATES:
            p = home / candidate
            if p.exists():
                return p
        return None

    def open_web(self) -> Dict:
        try:
            import webbrowser

            webbrowser.open(self.WEB_URL)
            return {"success": True, "url": self.WEB_URL}
        except Exception as e:
            return {"error": str(e)}

    def open_local_folder(self) -> Dict:
        folder = self.find_sync_folder()
        if not folder:
            return {
                "success": False,
                "error": "Local sync folder not found - is the desktop client installed and signed in?",
            }
        try:
            import os

            os.startfile(str(folder))
            return {"success": True, "path": str(folder)}
        except Exception as e:
            return {"error": str(e)}

    def upload_file(self, file_path: str) -> Dict:
        """Copies the file into the local sync folder, letting the desktop
        client sync it automatically. Falls back to opening the web
        uploader if no local sync folder is found."""
        folder = self.find_sync_folder()
        if not folder:
            self.open_web()
            return {
                "success": False,
                "error": "No local sync folder found - opened the web app instead; upload manually there",
            }
        try:
            dest = folder / Path(file_path).name
            shutil.copy2(file_path, dest)
            return {
                "success": True,
                "synced_to": str(dest),
                "note": "will finish uploading once the desktop client syncs it",
            }
        except Exception as e:
            return {"error": str(e)}
