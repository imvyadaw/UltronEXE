"""Hidden Files
===============
Two distinct layers of "hidden" on Windows, both covered here:
  1. Per-file: the hidden (and optionally system) file attribute, set via
     `attrib`. Controls whether *that specific file* shows up.
  2. Explorer-wide: the "Show hidden files/folders" setting, stored in
     HKCU...Explorer\\Advanced (Hidden=1 show / Hidden=2 don't) plus the
     separate "Hide protected operating system files" toggle
     (ShowSuperHidden). Controls what Explorer shows *at all*, regardless
     of individual file attributes.

hide()/hide_and_protect() and the Explorer-wide toggles are confirm-gated:
hiding a file (or hiding hidden files from view) can make something the
user relies on quietly disappear from normal browsing.
"""

import ctypes
import subprocess
from pathlib import Path
from typing import Dict, List

try:
    import winreg

    HAS_WINREG = True
except ImportError:
    HAS_WINREG = False

FILE_ATTRIBUTE_HIDDEN = 0x2
FILE_ATTRIBUTE_SYSTEM = 0x4
_ADV_KEY = r"Software\Microsoft\Windows\CurrentVersion\Explorer\Advanced"


class HiddenFiles:
    """Inspect/toggle per-file hidden+system attributes and the Explorer
    "show hidden items" setting."""

    def _run_attrib(self, args: list) -> Dict:
        try:
            result = subprocess.run(["attrib"] + args, capture_output=True, text=True, timeout=15)
            if result.returncode != 0:
                return {"error": result.stderr.strip() or result.stdout.strip() or "attrib failed"}
            return {"success": True, "stdout": result.stdout.strip()}
        except FileNotFoundError:
            return {"error": "attrib not found - this is only available on Windows"}
        except subprocess.TimeoutExpired:
            return {"error": "attrib timed out"}
        except Exception as e:
            return {"error": str(e)}

    def is_hidden(self, path: str) -> Dict:
        """Check whether a file/folder currently has the hidden attribute."""
        p = Path(path)
        if not p.exists():
            return {"error": f"Path not found: {path}"}
        try:
            attrs = ctypes.windll.kernel32.GetFileAttributesW(str(p))
        except AttributeError:
            return {"error": "Windows-only (ctypes.windll not available)"}
        if attrs == -1:
            return {"error": "Could not read file attributes"}
        return {
            "success": True,
            "path": str(p),
            "hidden": bool(attrs & FILE_ATTRIBUTE_HIDDEN),
            "system": bool(attrs & FILE_ATTRIBUTE_SYSTEM),
        }

    def list_hidden(self, folder: str) -> Dict:
        """List hidden files/folders directly inside `folder` (non-recursive)."""
        p = Path(folder)
        if not p.exists() or not p.is_dir():
            return {"error": f"Not a directory: {folder}"}
        hidden: List[str] = []
        for child in p.iterdir():
            check = self.is_hidden(str(child))
            if check.get("hidden"):
                hidden.append(str(child))
        return {"success": True, "folder": str(p), "hidden_items": hidden, "count": len(hidden)}

    def hide(self, path: str, confirm: bool = False) -> Dict:
        """Set the hidden attribute on a file/folder. Confirm-gated."""
        p = Path(path)
        if not p.exists():
            return {"error": f"Path not found: {path}"}
        if not confirm:
            return {
                "success": False,
                "needs_confirmation": True,
                "preview": f"Would hide {p} (adds the hidden attribute).",
                "message": "Call again with confirm=true to hide.",
            }
        return self._run_attrib(["+h", str(p)])

    def unhide(self, path: str, confirm: bool = False) -> Dict:
        """Clear the hidden (and system, if set) attribute on a file/folder.
        Confirm-gated."""
        p = Path(path)
        if not p.exists():
            return {"error": f"Path not found: {path}"}
        if not confirm:
            return {
                "success": False,
                "needs_confirmation": True,
                "preview": f"Would unhide {p}.",
                "message": "Call again with confirm=true to unhide.",
            }
        return self._run_attrib(["-h", "-s", str(p)])

    def hide_and_protect(self, path: str, confirm: bool = False) -> Dict:
        """Set both hidden AND system attributes - stronger hiding that also
        makes Explorer treat it as a protected OS file (excluded even when
        "show hidden files" is on, unless "hide protected OS files" is also
        off). Confirm-gated; system-protect a file the user still needs and
        it becomes genuinely hard to find again."""
        p = Path(path)
        if not p.exists():
            return {"error": f"Path not found: {path}"}
        if not confirm:
            return {
                "success": False,
                "needs_confirmation": True,
                "preview": f"Would mark {p} hidden AND system-protected - it will stay "
                f"invisible even with 'show hidden files' turned on.",
                "message": "Call again with confirm=true to apply.",
            }
        return self._run_attrib(["+h", "+s", str(p)])

    def get_explorer_hidden_setting(self) -> Dict:
        """Read the current HKCU Explorer 'show hidden files' + 'hide
        protected OS files' settings."""
        if not HAS_WINREG:
            return {"error": "winreg not available - this is only available on Windows"}
        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, _ADV_KEY)
            hidden_val, _ = winreg.QueryValueEx(key, "Hidden")
            try:
                super_hidden_val, _ = winreg.QueryValueEx(key, "ShowSuperHidden")
            except FileNotFoundError:
                super_hidden_val = 0
            winreg.CloseKey(key)
            return {
                "success": True,
                "show_hidden_files": hidden_val == 1,
                "show_protected_os_files": bool(super_hidden_val),
            }
        except Exception as e:
            return {"error": str(e)}

    def set_explorer_hidden_setting(self, show_hidden: bool, confirm: bool = False) -> Dict:
        """Toggle whether Explorer shows hidden files/folders at all
        (does not touch individual file attributes). Confirm-gated;
        applies immediately to open Explorer windows after a refresh."""
        if not HAS_WINREG:
            return {"error": "winreg not available - this is only available on Windows"}
        if not confirm:
            return {
                "success": False,
                "needs_confirmation": True,
                "preview": f"Would set Explorer to {'show' if show_hidden else 'hide'} " f"hidden files/folders.",
                "message": "Call again with confirm=true to apply.",
            }
        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, _ADV_KEY, 0, winreg.KEY_SET_VALUE)
            winreg.SetValueEx(key, "Hidden", 0, winreg.REG_DWORD, 1 if show_hidden else 2)
            winreg.CloseKey(key)
            subprocess.run(["ie4uinit.exe", "-show"], capture_output=True, timeout=10)
            return {
                "success": True,
                "show_hidden_files": show_hidden,
                "note": "Restart Explorer (or sign out) if open windows don't refresh.",
            }
        except Exception as e:
            return {"error": str(e)}
