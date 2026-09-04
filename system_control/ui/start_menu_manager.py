"""Start Menu Manager
=====================
Reads and controls Start menu content settings - the switches under
Settings > Personalization > Start - plus layout export/import and
best-effort pin/unpin. Per-user registry:
HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Explorer\\Advanced
(Start_TrackDocs, Start_TrackProgs, Start_IrisRecommendations). No
admin needed for the settings; layout import needs admin.

Layout export/import uses the built-in Export-StartLayout /
Import-StartLayout PowerShell cmdlets. These are fully supported on
Windows 10; on Windows 11 they only affect the legacy layout format
and Microsoft has not shipped an equivalent for the Windows 11 Start
layout (pinned/recommended grid) as of this writing - export/import
here will run but may not reflect what Windows 11 actually shows.

Pin/unpin use the Shell.Application COM "Pin to Start"/"Unpin from
Start" verbs. This is the same mechanism Explorer's own right-click
menu uses, but it is an unofficial/unsupported verb Microsoft can
remove or rename between builds - treat pin/unpin as best-effort, and
check the returned result for whether the verb was found.

Distinct from taskbar_manager.py (taskbar itself) and from the
top-level ui/ package (ULTRON's own interface, not the Windows Start
menu).

Content-setting toggles are per-user cosmetic preferences - not
confirm-gated. Layout import replaces Start's pinned/recommended
content and needs admin, so it IS confirm-gated. Pin/unpin are
mechanical, reversible, single-app actions - not confirm-gated.
"""

import subprocess
from typing import Dict, Optional


class StartMenuManager:
    """Inspect and control Start menu content settings, layout, and app pinning."""

    _ADV_KEY = r"HKCU\Software\Microsoft\Windows\CurrentVersion\Explorer\Advanced"

    def _run_ps(self, script: str, timeout: float = 20.0) -> Dict:
        try:
            result = subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            return {
                "success": result.returncode == 0,
                "stdout": result.stdout.strip(),
                "stderr": result.stderr.strip(),
            }
        except FileNotFoundError:
            return {"error": "powershell not found - this is only available on Windows"}
        except subprocess.TimeoutExpired:
            return {"error": "Command timed out"}
        except Exception as e:
            return {"error": str(e)}

    def _admin_hint(self, err: str) -> str:
        if err and ("denied" in err.lower() or "elevat" in err.lower() or "access is denied" in err.lower()):
            return err + " - this needs ULTRON running as Administrator."
        return err

    def _read_dword(self, name: str) -> Optional[int]:
        script = (
            f'(Get-ItemProperty -Path "Registry::{self._ADV_KEY}" -Name {name} -ErrorAction SilentlyContinue).{name}'
        )
        result = self._run_ps(script)
        if "error" in result or not result.get("success"):
            return None
        raw = result["stdout"].strip()
        try:
            return int(raw)
        except (ValueError, TypeError):
            return None

    def _write_dword(self, name: str, value: int) -> Dict:
        script = (
            f'New-Item -Path "Registry::{self._ADV_KEY}" -Force | Out-Null; '
            f'Set-ItemProperty -Path "Registry::{self._ADV_KEY}" -Name {name} -Value {value} -Type DWord -Force'
        )
        result = self._run_ps(script)
        if "error" in result:
            return result
        if not result["success"]:
            return {"error": result["stderr"] or f"Failed to set {name}."}
        return {"success": True}

    def get_settings(self) -> Dict:
        """Read Start menu content settings: show recently opened items
        (in Jump Lists/Start/Explorer), show most-used apps, and show
        recommended/recently-used files (Windows 11's 'Recommended'
        section)."""
        recent_docs = self._read_dword("Start_TrackDocs")
        recent_progs = self._read_dword("Start_TrackProgs")
        recommendations = self._read_dword("Start_IrisRecommendations")
        return {
            "show_recent_items": bool(recent_docs) if recent_docs is not None else None,
            "show_frequently_used_apps": bool(recent_progs) if recent_progs is not None else None,
            "show_recommended_files": bool(recommendations) if recommendations is not None else None,
        }

    def set_show_recent_items(self, enabled: bool, confirm: bool = False) -> Dict:
        """Turn 'show recently opened items in Jump Lists, Start, and
        File Explorer' on/off. Not confirm-gated."""
        result = self._write_dword("Start_TrackDocs", 1 if enabled else 0)
        if "error" in result:
            return result
        return {"success": True, "show_recent_items": enabled}

    def set_show_frequently_used_apps(self, enabled: bool, confirm: bool = False) -> Dict:
        """Turn 'show most used apps' on/off. Not confirm-gated."""
        result = self._write_dword("Start_TrackProgs", 1 if enabled else 0)
        if "error" in result:
            return result
        return {"success": True, "show_frequently_used_apps": enabled}

    def set_show_recommended_files(self, enabled: bool, confirm: bool = False) -> Dict:
        """Turn Windows 11's 'Recommended' section (recently used/
        suggested files) on/off. Not confirm-gated."""
        result = self._write_dword("Start_IrisRecommendations", 0 if enabled else 1)
        if "error" in result:
            return result
        return {"success": True, "show_recommended_files": enabled}

    def export_layout(self, export_path: str) -> Dict:
        """Export the current Start layout to an XML file via
        Export-StartLayout. Fully supported on Windows 10; on Windows 11
        it captures the legacy layout format only. No admin needed."""
        if not export_path:
            return {"error": "export_path is required."}
        result = self._run_ps(f"Export-StartLayout -Path '{export_path}'")
        if "error" in result:
            return result
        if not result["success"]:
            return {"error": self._admin_hint(result["stderr"] or "Export-StartLayout failed.")}
        return {"success": True, "exported_to": export_path}

    def import_layout(self, layout_path: str, confirm: bool = False) -> Dict:
        """Apply a Start layout XML (from export_layout or a provisioned
        template) via Import-StartLayout. Confirm-gated - replaces the
        current Start pinned content - and needs admin. Windows 11 note:
        Microsoft has not published an Import-StartLayout equivalent for
        the Windows 11 Start grid, so results on Windows 11 may not
        match what the Settings app / Start actually shows."""
        if not layout_path:
            return {"error": "layout_path is required."}
        if not confirm:
            return {
                "requires_confirmation": True,
                "preview": f"This will replace the current Start menu pinned layout with '{layout_path}'.",
            }
        result = self._run_ps(f"Import-StartLayout -LayoutPath '{layout_path}' -MountPath $env:SystemDrive\\")
        if "error" in result:
            return result
        if not result["success"]:
            return {"error": self._admin_hint(result["stderr"] or "Import-StartLayout failed.")}
        return {
            "success": True,
            "imported_from": layout_path,
            "note": "Windows 11 may not fully reflect this - Microsoft has no public API for the Win11 Start grid.",
        }

    def pin_app(self, app_path: str) -> Dict:
        """Best-effort pin an app/shortcut to Start via the unofficial
        Shell.Application 'Pin to Start' verb. Not confirm-gated -
        single reversible action. Returns found=False if the verb isn't
        present on this Windows build (Microsoft can remove/rename it)."""
        if not app_path:
            return {"error": "app_path is required."}
        script = (
            f"$sa = New-Object -ComObject Shell.Application; "
            f"$folder = $sa.Namespace((Split-Path '{app_path}')); "
            f"$item = $folder.ParseName((Split-Path '{app_path}' -Leaf)); "
            f"$verb = $item.Verbs() | Where-Object {{ $_.Name -replace '&','' -match 'Pin to Start' }}; "
            f"if ($verb) {{ $verb.DoIt(); Write-Output 'FOUND' }} else {{ Write-Output 'NOTFOUND' }}"
        )
        result = self._run_ps(script)
        if "error" in result:
            return result
        if not result["success"]:
            return {"error": result["stderr"] or "Pin action failed."}
        found = "FOUND" in result["stdout"]
        return {
            "success": found,
            "app_path": app_path,
            "note": (
                None
                if found
                else "The 'Pin to Start' verb was not found on this app/Windows build - unofficial API, best-effort only."
            ),
        }

    def unpin_app(self, app_path: str) -> Dict:
        """Best-effort unpin an app from Start via the unofficial
        Shell.Application 'Unpin from Start' verb. Not confirm-gated.
        Returns found=False if the verb isn't present."""
        if not app_path:
            return {"error": "app_path is required."}
        script = (
            f"$sa = New-Object -ComObject Shell.Application; "
            f"$folder = $sa.Namespace((Split-Path '{app_path}')); "
            f"$item = $folder.ParseName((Split-Path '{app_path}' -Leaf)); "
            f"$verb = $item.Verbs() | Where-Object {{ $_.Name -replace '&','' -match 'Unpin from Start' }}; "
            f"if ($verb) {{ $verb.DoIt(); Write-Output 'FOUND' }} else {{ Write-Output 'NOTFOUND' }}"
        )
        result = self._run_ps(script)
        if "error" in result:
            return result
        if not result["success"]:
            return {"error": result["stderr"] or "Unpin action failed."}
        found = "FOUND" in result["stdout"]
        return {
            "success": found,
            "app_path": app_path,
            "note": (
                None
                if found
                else "The 'Unpin from Start' verb was not found on this app/Windows build - unofficial API, best-effort only."
            ),
        }

    def open_start_menu(self) -> Dict:
        """Open the Start menu by simulating the Windows key press. Not
        confirm-gated - a UI navigation action, same class as any other
        "open X" tool."""
        try:
            import ctypes

            VK_LWIN = 0x5B
            KEYEVENTF_KEYUP = 0x0002
            ctypes.windll.user32.keybd_event(VK_LWIN, 0, 0, 0)
            ctypes.windll.user32.keybd_event(VK_LWIN, 0, KEYEVENTF_KEYUP, 0)
            return {"success": True}
        except AttributeError:
            return {"error": "ctypes.windll is only available on Windows."}
        except Exception as e:
            return {"error": str(e)}
