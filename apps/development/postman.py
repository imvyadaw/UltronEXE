"""Postman automation (desktop app - opens it and/or a shared collection URL)."""

import webbrowser
from typing import Dict

from apps.base_app import BaseApp


class PostmanApp(BaseApp):
    """Open Postman, or a shared collection link, for API testing."""

    APP_NAME = "postman"
    PROCESS_NAMES = ["postman.exe", "postman"]
    EXE_HINTS = ["postman", "postman.exe"]

    def open_collection_link(self, collection_url: str) -> Dict:
        try:
            webbrowser.open(collection_url)
            return {"success": True, "collection_url": collection_url}
        except Exception as e:
            return {"error": str(e)}
