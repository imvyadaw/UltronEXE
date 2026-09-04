"""Cross-browser automation: active-browser detection & delegation
(automation.py), generic hotkey-driven tab control (tab_manager.py),
keyboard-driven form filling (form_filler.py), and unified download
management (download_manager.py)."""

from browser.automation.automation import BrowserAutomation
from browser.automation.tab_manager import GenericTabManager
from browser.automation.form_filler import FormFiller
from browser.automation.download_manager import DownloadManager

__all__ = ["BrowserAutomation", "GenericTabManager", "FormFiller", "DownloadManager"]
