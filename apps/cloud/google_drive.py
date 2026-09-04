"""Google Drive automation (local sync-folder upload + web app)."""

from typing import Dict

from apps.cloud._sync_folder_base import SyncFolderApp


class GoogleDriveApp(SyncFolderApp):
    """Open Drive, browse the local sync folder, and drop files to upload."""

    APP_NAME = "google drive"
    PROCESS_NAMES = ["googledrivefs.exe", "drivefs", "google drive"]
    EXE_HINTS = ["googledrivefs", "googledrivefs.exe"]
    SYNC_FOLDER_CANDIDATES = ["Google Drive", "GoogleDrive", "My Drive"]
    WEB_URL = "https://drive.google.com"

    def new_folder_web(self, name: str) -> Dict:
        """Google Drive has no simple URL scheme for creating a named
        folder, so this opens Drive - the caller/AI should follow up with
        UI automation or the Drive API for a fully headless version."""
        opened = self.open_web()
        return {**opened, "requested_folder_name": name, "note": "create the folder manually or via the Drive API"}
