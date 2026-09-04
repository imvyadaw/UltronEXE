"""Cloud storage automations: Google Drive, OneDrive, Dropbox, MEGA."""

from apps.cloud.google_drive import GoogleDriveApp
from apps.cloud.onedrive import OneDriveApp
from apps.cloud.dropbox import DropboxApp
from apps.cloud.mega import MegaApp

__all__ = ["GoogleDriveApp", "OneDriveApp", "DropboxApp", "MegaApp"]
