"""
Windows control facade
=======================
Composes every domain module under windows/, files/, browser/ and automation/
into a single object with the same flat method surface the old monolithic
SystemTools class had. This keeps ai/router.py's tool dispatch table stable
while the actual logic now lives in properly separated modules.
"""

from pathlib import Path
from typing import Dict, Optional

from windows.apps.manager import get_app_manager
from windows.apps.uninstaller import AppUninstaller
from windows.audio.volume import VolumeControl
from windows.audio.media_keys import MediaKeys
from windows.display.monitor import DisplayMonitor
from windows.system_info.diagnostics import SystemDiagnostics
from windows.system_info.power import PowerControl
from windows.cmd.runner import CommandRunner
from files.manager.manager import FileManager
from browser.chrome.chrome import ChromeController
from automation.clipboard.clipboard import ClipboardControl
from automation.keyboard.keyboard import KeyboardControl
from skills.internet.weather import WeatherLookup
from memory.short_term.notes import NotesStore

from files.pdf.pdf import PDFTools
from files.office.office import OfficeTools
from files.compression.compression import CompressionTools
from files.search.indexed_search import IndexedSearch
from windows.process.manager import ProcessManager
from windows.registry.editor import RegistryEditor
from windows.services.controller import ServiceController
from windows.startup.startup import StartupTools
from windows.notifications.toasts import ToastNotifier
from windows.firewall.rules import FirewallRules
from windows.defender.scanner import DefenderScanner
from windows.explorer.file_ops import ExplorerFileOps
from windows.powershell.executor import PowerShellExecutor
from browser.edge.edge import EdgeController
from browser.firefox.firefox import FirefoxController
from browser.cookies.cookies import CookieTools
from browser.downloads.downloads import DownloadsTools
from browser.automation.automation import BrowserAutomation
from automation.mouse.mouse import MouseControl
from automation.macro.macro import MacroRecorder
from automation.workflow.workflow import WorkflowRunner
from automation.ui.ui_automation import UIAutomation
from memory.history.history import ConversationHistoryStore
from memory.long_term.long_term import LongTermMemory
from memory.vector_db.vector_store import VectorStore
from vision.ocr.tesseract_ocr import OCR
from vision.face.detection import FaceDetector as FaceRecognizer
from vision.object_detection.yolo_detector import ObjectDetector
from vision.ui_detection.element_locator import UIDetector
from agents.coding_agent import CodingAgent

from windows.window_manager import WindowManager
from windows.virtual_desktop import VirtualDesktopManager
from windows.power_management import PowerManager
from windows.accessibility import AccessibilityTools
from browser.bookmark_manager import BookmarkManager
from browser.history_analyzer import HistoryAnalyzer
from browser.tab_manager import TabManager
from browser.form_filler import FormFiller


class SystemTools:
    """Full Windows control surface - same public API as before the restructure,
    now backed by focused modules instead of one 1100-line file."""

    def __init__(self):
        self.home_dir = Path.home()
        self.current_dir = self.home_dir

        self._apps = get_app_manager()
        self._app_uninstaller = AppUninstaller()
        self._volume = VolumeControl()
        self._media = MediaKeys()
        self._display = DisplayMonitor()
        self._status = SystemDiagnostics()
        self._power = PowerControl()
        self._cmd = CommandRunner()
        self._files = FileManager()
        self._chrome = ChromeController()
        self._clipboard = ClipboardControl()
        self._keyboard = KeyboardControl()
        self._weather = WeatherLookup()
        self._notes = NotesStore()

        self._pdf = PDFTools()
        self._office = OfficeTools()
        self._compression = CompressionTools()
        self._indexed_search = IndexedSearch()
        self._process = ProcessManager()
        self._registry = RegistryEditor()
        self._services = ServiceController()
        self._startup = StartupTools()
        self._notifications = ToastNotifier()
        self._firewall = FirewallRules()
        self._defender = DefenderScanner()
        self._explorer = ExplorerFileOps()
        self._powershell = PowerShellExecutor()
        self._edge = EdgeController()
        self._firefox = FirefoxController()
        self._cookies = CookieTools()
        self._downloads = DownloadsTools()
        self._browser_automation = BrowserAutomation()
        self._mouse = MouseControl()
        self._macro = MacroRecorder()
        self._workflow = WorkflowRunner()
        self._ui_automation = UIAutomation()
        self._history = ConversationHistoryStore()
        self._long_term = LongTermMemory()
        self._vector_store = VectorStore()
        self._ocr = OCR()
        self._faces = FaceRecognizer()
        self._objects = ObjectDetector()
        self._ui_detector = UIDetector()
        self._coding_agent = CodingAgent()

        # Deferred import: skills/app_control/app_manager.py imports
        # windows.apps.manager, which (as a submodule of this package)
        # requires windows/__init__.py to already be running - importing
        # AppControlManager at module load time here creates a cycle if
        # something imports skills.app_control.app_manager before the
        # windows package. Importing it here, at first use, breaks the cycle.
        from skills.app_control.app_manager import AppControlManager

        self._app_control = AppControlManager()
        self._window_manager = WindowManager()
        self._virtual_desktop = VirtualDesktopManager()
        self._power_management = PowerManager()
        self._accessibility = AccessibilityTools()
        self._bookmarks = BookmarkManager()
        self._history_analyzer = HistoryAnalyzer()
        self._tab_manager = TabManager()
        self._form_filler = FormFiller()

        self._parts = [
            self._apps,
            self._app_uninstaller,
            self._volume,
            self._media,
            self._display,
            self._status,
            self._power,
            self._cmd,
            self._files,
            self._chrome,
            self._clipboard,
            self._keyboard,
            self._weather,
            self._notes,
            self._pdf,
            self._office,
            self._compression,
            self._indexed_search,
            self._process,
            self._registry,
            self._services,
            self._startup,
            self._notifications,
            self._firewall,
            self._defender,
            self._explorer,
            self._powershell,
            self._edge,
            self._firefox,
            self._cookies,
            self._downloads,
            self._browser_automation,
            self._mouse,
            self._macro,
            self._workflow,
            self._ui_automation,
            self._history,
            self._long_term,
            self._vector_store,
            self._ocr,
            self._app_control,
            self._window_manager,
            self._virtual_desktop,
            self._power_management,
            self._accessibility,
            self._bookmarks,
            self._history_analyzer,
            self._tab_manager,
            self._form_filler,
        ]

    # --- Vision (explicit methods - avoid generic names like "detect"
    # colliding across face/object/gesture modules in __getattr__ below) ---
    def detect_faces_on_screen(self) -> Dict:
        return self._faces.detect_faces()

    def detect_objects_on_screen(self, confidence_threshold: float = 0.4) -> Dict:
        return self._objects.detect(confidence_threshold=confidence_threshold)

    def find_ui_text_regions(self) -> Dict:
        return self._ui_detector.find_text_regions()

    # --- Coding agent ------------------------------------------------------
    def write_code(self, spec: str, language: str = None) -> Dict:
        return self._coding_agent.write_code(spec, language=language)

    def review_code(self, code: str) -> Dict:
        return self._coding_agent.review_code(code)

    def fix_code(self, code: str, error_message: str = None) -> Dict:
        return self._coding_agent.fix_code(code, error_message=error_message)

    def explain_code(self, code: str) -> Dict:
        return self._coding_agent.explain_code(code)

    def __getattr__(self, name):
        # Delegate any tool method (open_application, list_directory, set_volume, ...)
        # to whichever domain part actually implements it.
        for part in self._parts:
            if hasattr(part, name):
                attr = getattr(part, name)
                if callable(attr):
                    return attr
        raise AttributeError(f"SystemTools has no attribute '{name}'")


_system_tools: Optional[SystemTools] = None


def get_system_tools() -> SystemTools:
    global _system_tools
    if _system_tools is None:
        _system_tools = SystemTools()
    return _system_tools
