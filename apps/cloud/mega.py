"""MEGA automation (local MEGAsync folder upload + web app)."""

from apps.cloud._sync_folder_base import SyncFolderApp


class MegaApp(SyncFolderApp):
    """Open MEGA, browse the local MEGAsync folder, and drop files to upload."""

    APP_NAME = "mega"
    PROCESS_NAMES = ["megasync.exe", "megasync"]
    EXE_HINTS = ["megasync", "megasync.exe"]
    SYNC_FOLDER_CANDIDATES = ["MEGA", "MEGAsync"]
    WEB_URL = "https://mega.nz/fm"
