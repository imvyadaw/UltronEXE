"""
Base app automation (Phase 6)
==============================
Common class every apps/* automation module inherits from. Wraps
windows/apps/manager.py's AppManager for open/close/is_running/focus,
pyautogui for keystrokes, and the Windows "App Paths" registry / PATH
for resolving a real executable when a module needs to pass command-line
flags (e.g. --incognito, a file path, a project folder) that
AppManager.open_application()'s plain os.startfile() can't.

Every method returns a Dict, matching the {"success": True, ...} /
{"error": "..."} convention used across the rest of the codebase, so
apps/* automations drop straight into ai/apps_tools.py the same way
skills/* and integration/* do.
"""

import shutil
import subprocess
import time
from typing import Dict, List, Optional

from windows.apps.manager import get_app_manager, HAS_PSUTIL, HAS_PYGETWINDOW

if HAS_PSUTIL:
    import psutil
if HAS_PYGETWINDOW:
    import pygetwindow as gw

try:
    import pyautogui

    pyautogui.FAILSAFE = False
    HAS_PYAUTOGUI = True
except ImportError:
    HAS_PYAUTOGUI = False


class BaseApp:
    """Common automation surface for a single desktop/web application.

    Subclasses set:
      APP_NAME      - name AppManager/AppLauncher already know how to
                       resolve (Start Menu shortcut search term, and a
                       key in windows/apps/manager.py's APP_ALIASES).
      PROCESS_NAMES - process name substrings used for is_running/close
                       (falls back to [APP_NAME] if left empty).
      EXE_HINTS     - executable names to try via shutil.which() when a
                       module needs the real exe path to pass arguments
                       (falls back to [APP_NAME] if left empty).
    """

    APP_NAME: str = ""
    PROCESS_NAMES: List[str] = []
    EXE_HINTS: List[str] = []

    def __init__(self):
        self._apps = get_app_manager()

    # -- lifecycle -----------------------------------------------------
    def open(self) -> Dict:
        """Launch the app via its Start Menu shortcut / App Paths entry."""
        try:
            return self._apps.open_application(self.APP_NAME)
        except Exception as e:
            return {"error": str(e)}

    def close(self) -> Dict:
        """Close the app (kills the matching process)."""
        try:
            return self._apps.close_application(self.APP_NAME)
        except Exception as e:
            return {"error": str(e)}

    def is_running(self) -> Dict:
        """Check whether a process matching this app is currently running."""
        if not HAS_PSUTIL:
            return {"error": "psutil not installed - run: pip install psutil"}
        try:
            names = [n.lower().replace(".exe", "") for n in (self.PROCESS_NAMES or [self.APP_NAME])]
            for proc in psutil.process_iter(["name"]):
                pname = (proc.info.get("name") or "").lower().replace(".exe", "")
                if any(n in pname for n in names):
                    return {"app": self.APP_NAME, "running": True, "process_name": proc.info["name"]}
            return {"app": self.APP_NAME, "running": False}
        except Exception as e:
            return {"error": str(e)}

    def focus(self) -> Dict:
        """Bring the app's window to the foreground."""
        if not HAS_PYGETWINDOW:
            return {"error": "pygetwindow not installed - run: pip install pygetwindow"}
        try:
            query = self.APP_NAME.lower()
            for title in gw.getAllTitles():
                if title.strip() and query in title.lower():
                    win = gw.getWindowsWithTitle(title)[0]
                    win.activate()
                    return {"success": True, "focused": title}
            return {"success": False, "error": f"No open window matching '{self.APP_NAME}'"}
        except Exception as e:
            return {"error": str(e)}

    def wait_for_window(self, timeout: float = 10.0) -> Dict:
        """Block until a window matching APP_NAME appears (or timeout)."""
        if not HAS_PYGETWINDOW:
            return {"error": "pygetwindow not installed - run: pip install pygetwindow"}
        query = self.APP_NAME.lower()
        deadline = time.time() + timeout
        while time.time() < deadline:
            for title in gw.getAllTitles():
                if title.strip() and query in title.lower():
                    return {"found": True, "title": title}
            time.sleep(0.3)
        return {"found": False}

    # -- executable resolution / raw launching --------------------------
    def resolve_executable(self) -> Optional[str]:
        """Best-effort real .exe path, needed when a module has to pass
        command-line flags (open_application() alone can't)."""
        try:
            exe = self._apps._find_via_app_paths_registry(self.APP_NAME)
            if exe:
                return exe
        except Exception:
            from core.error_trace import log_swallowed as _lsw

            _lsw("apps.base_app.resolve_executable")
        for hint in self.EXE_HINTS or [self.APP_NAME]:
            found = shutil.which(hint)
            if found:
                return found
        return None

    def run_command(self, args: List[str]) -> Dict:
        """Launch a process directly (real exe + arbitrary CLI args)."""
        try:
            subprocess.Popen(args)
            return {"success": True, "command": args}
        except Exception as e:
            return {"error": str(e)}

    def run_and_capture(self, args: List[str], timeout: float = 30.0) -> Dict:
        """Run a CLI command and wait for its output (for CLI-driven tools
        like git/docker/powershell rather than GUI apps)."""
        try:
            result = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
            return {
                "success": result.returncode == 0,
                "returncode": result.returncode,
                "stdout": result.stdout.strip(),
                "stderr": result.stderr.strip(),
            }
        except subprocess.TimeoutExpired:
            return {"error": f"Command timed out after {timeout}s"}
        except Exception as e:
            return {"error": str(e)}

    # -- keyboard automation (GUI apps that need a hotkey/typed text) ---
    def type_text(self, text: str) -> Dict:
        if not HAS_PYAUTOGUI:
            return {"error": "pyautogui not installed - run: pip install pyautogui"}
        try:
            pyautogui.typewrite(text, interval=0.01)
            return {"success": True, "typed": text}
        except Exception as e:
            return {"error": str(e)}

    def press_key(self, key: str) -> Dict:
        """Press a key or combo (e.g. 'enter', 'ctrl+s') in the focused window."""
        if not HAS_PYAUTOGUI:
            return {"error": "pyautogui not installed - run: pip install pyautogui"}
        try:
            if "+" in key:
                pyautogui.hotkey(*[k.strip() for k in key.split("+")])
            else:
                pyautogui.press(key)
            return {"success": True, "key": key}
        except Exception as e:
            return {"error": str(e)}

    def type_and_send(self, text: str, focus_first: bool = True) -> Dict:
        """Focus the app, type text into whatever's focused, hit Enter.
        The common pattern behind "send a message" in chat apps that don't
        expose a real send API (Signal, Discord, Slack UI fallback, ...)."""
        if focus_first:
            focus_result = self.focus()
            if focus_result.get("error"):
                return focus_result
            time.sleep(0.4)
        typed = self.type_text(text)
        if typed.get("error"):
            return typed
        time.sleep(0.1)
        return self.press_key("enter")

    def screenshot_window(self) -> Dict:
        """Best-effort full-screen screenshot as a fallback when there's no
        API for "show me what this app looks like right now"."""
        if not HAS_PYAUTOGUI:
            return {"error": "pyautogui not installed - run: pip install pyautogui"}
        try:
            from config import BASE_DIR

            out_dir = BASE_DIR / "storage" / "exports"
            out_dir.mkdir(parents=True, exist_ok=True)
            path = out_dir / f"{self.APP_NAME}_{int(time.time())}.png"
            pyautogui.screenshot(str(path))
            return {"success": True, "path": str(path)}
        except Exception as e:
            return {"error": str(e)}
