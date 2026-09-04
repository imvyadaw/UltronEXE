"""Windows Settings app automation (via ms-settings: URI scheme)."""

import webbrowser
from typing import Dict

from apps.base_app import BaseApp

PAGES = {
    "display": "ms-settings:display",
    "sound": "ms-settings:sound",
    "bluetooth": "ms-settings:bluetooth",
    "wifi": "ms-settings:network-wifi",
    "update": "ms-settings:windowsupdate",
    "storage": "ms-settings:storagesense",
    "battery": "ms-settings:batterysaver",
    "apps": "ms-settings:appsfeatures",
    "accounts": "ms-settings:yourinfo",
    "privacy": "ms-settings:privacy",
    "notifications": "ms-settings:notifications",
    "personalization": "ms-settings:personalization",
    "about": "ms-settings:about",
}


class SettingsApp(BaseApp):
    """Open the Windows Settings app, optionally to a specific page."""

    APP_NAME = "settings"
    PROCESS_NAMES = ["systemsettings.exe", "settingsapp.exe"]
    EXE_HINTS = []

    def open_page(self, page: str) -> Dict:
        uri = PAGES.get(page.lower().replace(" ", "_"), f"ms-settings:{page}")
        try:
            webbrowser.open(uri)
            return {"success": True, "page": page}
        except Exception as e:
            return {"error": str(e)}

    def list_pages(self) -> Dict:
        return {"success": True, "pages": list(PAGES.keys())}
