"""Dropbox automation (local sync-folder upload + web app)."""

from apps.cloud._sync_folder_base import SyncFolderApp


class DropboxApp(SyncFolderApp):
    """Open Dropbox, browse the local sync folder, and drop files to upload."""

    APP_NAME = "dropbox"
    PROCESS_NAMES = ["dropbox.exe", "dropbox"]
    EXE_HINTS = ["dropbox", "dropbox.exe"]
    SYNC_FOLDER_CANDIDATES = ["Dropbox"]
    WEB_URL = "https://www.dropbox.com/home"
