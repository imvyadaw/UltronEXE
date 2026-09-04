"""File Associations
=====================
Query and change which program opens a given file extension. Reads go
through the registry directly (HKCU FileExts UserChoice, falling back to
HKCR) for an accurate picture; writes go through the classic
`assoc`/`ftype` commands.

Honest limitation, stated up front rather than discovered by a failed
call: on Windows 8+ the per-user "UserChoice" association is hash-
protected (the hash binds the choice to the specific user+extension+
ProgId+Windows build, to stop malware silently hijacking file types), so
`assoc`/`ftype` alone often can't force a UserChoice change on a modern
build - it reliably changes the machine-wide/legacy association and
frequently prompts Windows to fall back to it, but is not guaranteed to
override an explicit prior user choice. Every write method's result
includes this caveat and open_with_dialog() is offered as the reliable
fallback (native Windows UI, always works, just needs a click).

set_default_app/reset_association are confirm-gated - they change what
double-clicking a whole class of file does system-wide for that user.
"""
import logging

import subprocess
from typing import Dict, List, Optional

try:
    import winreg

    HAS_WINREG = True
except ImportError:
    HAS_WINREG = False

_UNDO_HINT = (
    "Modern Windows may not honor this for extensions with an existing "
    "user choice (hash-protected UserChoice) - if it doesn't take effect, "
    "use open_with_dialog() and pick 'Always use this app' instead."
)


class FileAssociations:
    """Inspect/change the default program for a file extension."""

    def _norm_ext(self, extension: str) -> str:
        ext = extension.strip().lower()
        return ext if ext.startswith(".") else f".{ext}"

    def get_default_app(self, extension: str) -> Dict:
        """Look up the program currently associated with an extension,
        preferring the per-user UserChoice registration and falling back
        to the classic HKCR ProgId/assoc chain."""
        ext = self._norm_ext(extension)
        if HAS_WINREG:
            try:
                key = winreg.OpenKey(
                    winreg.HKEY_CURRENT_USER,
                    rf"Software\Microsoft\Windows\CurrentVersion\Explorer\FileExts\{ext}\UserChoice",
                )
                prog_id, _ = winreg.QueryValueEx(key, "ProgId")
                winreg.CloseKey(key)
                return {"success": True, "extension": ext, "prog_id": prog_id, "source": "UserChoice"}
            except FileNotFoundError:
                logging.getLogger(__name__).exception("Suppressed FileNotFoundError")
            except Exception as e:
                return {"error": str(e)}
        result = subprocess.run(["assoc", ext], capture_output=True, text=True, timeout=10)
        if result.returncode != 0 or "=" not in (result.stdout or ""):
            return {"error": f"No association found for {ext}"}
        prog_id = result.stdout.strip().split("=", 1)[1]
        return {"success": True, "extension": ext, "prog_id": prog_id, "source": "assoc"}

    def list_associations(self, extensions: List[str]) -> Dict:
        """Batch version of get_default_app for a list of extensions -
        handy for surveying several types at once."""
        return {"success": True, "results": {e: self.get_default_app(e) for e in extensions}}

    def set_default_app(
        self, extension: str, prog_id: str, exe_path: Optional[str] = None, confirm: bool = False
    ) -> Dict:
        """Associate an extension with a ProgId (e.g. 'txtfile',
        'Applications\\notepad.exe'), and optionally define/refresh that
        ProgId's open command to point at exe_path. Confirm-gated. See
        module docstring for the UserChoice caveat on modern Windows."""
        ext = self._norm_ext(extension)
        if not prog_id:
            return {"error": "prog_id must be non-empty"}
        if not confirm:
            return {
                "success": False,
                "needs_confirmation": True,
                "preview": f"Would set {ext} to open with '{prog_id}'" f"{f' ({exe_path})' if exe_path else ''}.",
                "message": "Call again with confirm=true to apply.",
                "caveat": _UNDO_HINT,
            }
        errors = []
        r1 = subprocess.run(["cmd", "/c", "assoc", f"{ext}={prog_id}"], capture_output=True, text=True, timeout=10)
        if r1.returncode != 0:
            errors.append(r1.stderr.strip() or "assoc failed")
        if exe_path:
            r2 = subprocess.run(
                ["cmd", "/c", "ftype", f'{prog_id}="{exe_path}" "%1"'],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if r2.returncode != 0:
                errors.append(r2.stderr.strip() or "ftype failed")
        return {
            "success": not errors,
            "extension": ext,
            "prog_id": prog_id,
            "errors": errors or None,
            "caveat": _UNDO_HINT,
        }

    def reset_association(self, extension: str, confirm: bool = False) -> Dict:
        """Remove the custom association for an extension, reverting to
        whatever Windows falls back to by default. Confirm-gated."""
        ext = self._norm_ext(extension)
        if not confirm:
            return {
                "success": False,
                "needs_confirmation": True,
                "preview": f"Would reset the association for {ext} to the system default.",
                "message": "Call again with confirm=true to reset.",
                "caveat": _UNDO_HINT,
            }
        result = subprocess.run(["cmd", "/c", "assoc", f"{ext}="], capture_output=True, text=True, timeout=10)
        return {
            "success": result.returncode == 0,
            "extension": ext,
            "error": None if result.returncode == 0 else result.stderr.strip(),
            "caveat": _UNDO_HINT,
        }

    def open_with_dialog(self, path: str) -> Dict:
        """Open the native Windows 'Open with' picker for a specific file -
        the reliable way to change UserChoice on modern Windows (user picks
        an app and ticks 'Always use this app'). Not confirm-gated: it only
        opens a picker UI, it changes nothing by itself."""
        try:
            subprocess.Popen(["rundll32.exe", "shell32.dll,OpenAs_RunDLL", path])
            return {"success": True, "opened": True, "path": path}
        except FileNotFoundError:
            return {"error": "rundll32 not found - this is only available on Windows"}
        except Exception as e:
            return {"error": str(e)}
