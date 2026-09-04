"""Microsoft OneDrive automation (local sync-folder upload + web app)."""

from apps.cloud._sync_folder_base import SyncFolderApp


class OneDriveApp(SyncFolderApp):
    """Open OneDrive, browse the local sync folder, and drop files to upload."""

    APP_NAME = "onedrive"
    PROCESS_NAMES = ["onedrive.exe", "onedrive"]
    EXE_HINTS = ["onedrive", "onedrive.exe"]
    SYNC_FOLDER_CANDIDATES = ["OneDrive"]
    WEB_URL = "https://onedrive.live.com"
