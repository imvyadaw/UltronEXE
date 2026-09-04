"""Desktop Icon Manager
=======================
Reads and controls the Windows desktop icon layer - the same settings
under Settings > Personalization > Themes > Desktop icon settings,
plus right-click-on-desktop > View/Sort by. Two registry roots, both
HKCU, no admin needed:
  - HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Explorer\\Advanced:
    HideIcons (show/hide ALL desktop icons at once).
  - HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Explorer\\
    HideDesktopIcons\\NewStartPanel (+ \\ClassicStartMenu, kept in sync):
    per-icon DWORDs (0=show, 1=hide) for the 5 special icons - This PC,
    Recycle Bin, User's Files, Network, Control Panel.
  - HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Explorer\\
    Desktop\\WindowMetrics: Shell Icon Size (string, pixels).
  - HKCU\\Software\\Microsoft\\Windows\\Shell\\Bags\\1\\Desktop:
    FFlags bitmask (auto-arrange, align-to-grid bits).

Distinct from system_control/ui/taskbar_manager.py and
start_menu_manager.py (taskbar/Start, not the desktop surface itself).
Distinct from windows/display/monitor.py (screenshots/brightness/
resolution, not icon layout).

Per-icon visibility changes are pushed live via SHChangeNotify - no
sign-out needed. Icon size and auto-arrange/align-to-grid changes are
picked up by Explorer's own file-system-change watcher in most cases,
but a restart_explorer call (see uictl_taskbar_restart_explorer) is the
reliable way to force a repaint if one doesn't show up on its own.

All of these are per-user cosmetic/layout preferences, so none of them
are confirm-gated - same class as any other UI-preference toggle.
"""

import ctypes
import subprocess
from typing import Dict, Optional


class DesktopIconManager:
    """Inspect and control desktop icon visibility, size, and layout."""

    _ADVANCED_KEY = r"HKCU\Software\Microsoft\Windows\CurrentVersion\Explorer\Advanced"
    _HIDE_KEY_NEW = r"HKCU\Software\Microsoft\Windows\CurrentVersion\Explorer\HideDesktopIcons\NewStartPanel"
    _HIDE_KEY_CLASSIC = r"HKCU\Software\Microsoft\Windows\CurrentVersion\Explorer\HideDesktopIcons\ClassicStartMenu"
    _METRICS_KEY = r"HKCU\Software\Microsoft\Windows\CurrentVersion\Explorer\Desktop\WindowMetrics"
    _BAGS_KEY = r"HKCU\Software\Microsoft\Windows\Shell\Bags\1\Desktop"

    # The 5 special icons Windows lets you individually show/hide.
    _ICON_GUIDS = {
        "this_pc": "{20D04FE0-3AEA-1069-A2D8-08002B30309D}",
        "recycle_bin": "{645FF040-5081-101B-9F08-00AA002F954E}",
        "user_files": "{59031a47-3f72-44a7-89c5-5595fe6b30ee}",
        "network": "{F02C1A0D-BE21-4350-88B0-7367FC96EF3C}",
        "control_panel": "{5399E694-6CE5-4D6C-8FCE-1D8870FDCBA0}",
    }
    _ICON_SIZES_PX = {"small": 32, "medium": 48, "large": 96}
    # FFlags bits (undocumented but stable since XP): 0x20 = auto arrange,
    # 0x1000 = align to grid.
    _FFLAG_AUTO_ARRANGE = 0x20
    _FFLAG_ALIGN_TO_GRID = 0x1000

    def _run_ps(self, script: str, timeout: float = 15.0) -> Dict:
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

    def _read_value(self, key: str, name: str) -> Optional[str]:
        script = f'(Get-ItemProperty -Path "Registry::{key}" -Name "{name}" -ErrorAction SilentlyContinue)."{name}"'
        result = self._run_ps(script)
        if "error" in result or not result.get("success"):
            return None
        raw = result["stdout"].strip()
        return raw if raw else None

    def _write_dword(self, key: str, name: str, value: int) -> Dict:
        script = (
            f'New-Item -Path "Registry::{key}" -Force | Out-Null; '
            f'Set-ItemProperty -Path "Registry::{key}" -Name "{name}" -Value {value} -Type DWord -Force'
        )
        result = self._run_ps(script)
        if "error" in result:
            return result
        if not result["success"]:
            return {"error": result["stderr"] or f"Failed to set {name}."}
        return {"success": True}

    def _write_string(self, key: str, name: str, value: str) -> Dict:
        script = (
            f'New-Item -Path "Registry::{key}" -Force | Out-Null; '
            f'Set-ItemProperty -Path "Registry::{key}" -Name "{name}" -Value "{value}" -Type String -Force'
        )
        result = self._run_ps(script)
        if "error" in result:
            return result
        if not result["success"]:
            return {"error": result["stderr"] or f"Failed to set {name}."}
        return {"success": True}

    def _refresh_desktop(self) -> None:
        """Ask Explorer to repaint the desktop immediately, best-effort.
        SHCNE_ASSOCCHANGED + SHCNF_IDLIST is the standard trick to force
        a desktop-icon refresh without a full Explorer restart."""
        try:
            SHCNE_ASSOCCHANGED = 0x08000000
            SHCNF_IDLIST = 0x0000
            ctypes.windll.shell32.SHChangeNotify(SHCNE_ASSOCCHANGED, SHCNF_IDLIST, None, None)
        except Exception:
            pass  # purely cosmetic best-effort, never worth failing the call over

    # -- Show/hide everything --------------------------------------------
    def get_show_desktop_icons(self) -> Dict:
        """Read whether desktop icons are shown at all (right-click
        desktop > View > Show desktop icons)."""
        raw = self._read_value(self._ADVANCED_KEY, "HideIcons")
        hidden = raw == "1"
        return {"desktop_icons_visible": not hidden}

    def set_show_desktop_icons(self, visible: bool, confirm: bool = False) -> Dict:
        """Turn all desktop icons on/off in one go. Not confirm-gated."""
        result = self._write_dword(self._ADVANCED_KEY, "HideIcons", 0 if visible else 1)
        if "error" in result:
            return result
        self._refresh_desktop()
        return {"success": True, "desktop_icons_visible": visible}

    # -- Per-icon visibility ----------------------------------------------
    def list_icon_names(self) -> Dict:
        """List the special-icon names this manager can toggle individually."""
        return {"icons": sorted(self._ICON_GUIDS.keys())}

    def get_icon_visibility(self, icon: str) -> Dict:
        """Read whether one of the 5 special icons (this_pc, recycle_bin,
        user_files, network, control_panel) is shown on the desktop."""
        guid = self._ICON_GUIDS.get(icon.lower().strip())
        if not guid:
            return {"error": f"Unknown icon '{icon}'. Use list_icon_names for valid values."}
        raw = self._read_value(self._HIDE_KEY_NEW, guid)
        hidden = raw == "1"
        return {"icon": icon, "visible": not hidden}

    def set_icon_visibility(self, icon: str, visible: bool, confirm: bool = False) -> Dict:
        """Show or hide one of the 5 special desktop icons. Writes both
        the NewStartPanel and ClassicStartMenu keys, which Windows keeps
        in sync depending on view mode. Not confirm-gated."""
        guid = self._ICON_GUIDS.get(icon.lower().strip())
        if not guid:
            return {"error": f"Unknown icon '{icon}'. Use list_icon_names for valid values."}
        value = 0 if visible else 1
        r1 = self._write_dword(self._HIDE_KEY_NEW, guid, value)
        if "error" in r1:
            return r1
        self._write_dword(self._HIDE_KEY_CLASSIC, guid, value)  # best-effort, ignore failure
        self._refresh_desktop()
        return {"success": True, "icon": icon, "visible": visible}

    # -- Icon size ----------------------------------------------------------
    def get_icon_size(self) -> Dict:
        """Read the current desktop icon size in pixels (and its nearest
        small/medium/large label)."""
        raw = self._read_value(self._METRICS_KEY, "Shell Icon Size")
        try:
            px = int(raw) if raw else 32
        except (TypeError, ValueError):
            px = 32
        label = min(self._ICON_SIZES_PX, key=lambda k: abs(self._ICON_SIZES_PX[k] - px))
        return {"icon_size_px": px, "closest_label": label}

    def set_icon_size(self, size: str, confirm: bool = False) -> Dict:
        """Set desktop icon size: 'small' (32px), 'medium' (48px), or
        'large' (96px). Takes effect after the next Explorer repaint -
        call uictl_taskbar_restart_explorer if it doesn't appear
        immediately. Not confirm-gated."""
        px = self._ICON_SIZES_PX.get(size.lower().strip())
        if px is None:
            return {"error": "size must be 'small', 'medium', or 'large'."}
        result = self._write_string(self._METRICS_KEY, "Shell Icon Size", str(px))
        if "error" in result:
            return result
        self._refresh_desktop()
        return {
            "success": True,
            "icon_size": size,
            "icon_size_px": px,
            "note": "Restart Explorer (uictl_taskbar_restart_explorer) if the new size doesn't show immediately.",
        }

    # -- Layout: auto-arrange / align to grid --------------------------------
    def get_layout(self) -> Dict:
        """Read whether desktop icons are set to auto-arrange and/or
        align to grid."""
        raw = self._read_value(self._BAGS_KEY, "FFlags")
        try:
            flags = int(raw) if raw else 0
        except (TypeError, ValueError):
            flags = 0
        return {
            "auto_arrange": bool(flags & self._FFLAG_AUTO_ARRANGE),
            "align_to_grid": bool(flags & self._FFLAG_ALIGN_TO_GRID),
        }

    def set_layout(self, auto_arrange: bool = None, align_to_grid: bool = None, confirm: bool = False) -> Dict:
        """Turn 'Auto arrange icons' and/or 'Align icons to grid' on/off.
        Pass only the flags you want to change; the other stays as-is.
        Not confirm-gated - purely a layout preference. May need
        uictl_taskbar_restart_explorer to visibly repaint."""
        current = self.get_layout()
        new_auto = current["auto_arrange"] if auto_arrange is None else auto_arrange
        new_grid = current["align_to_grid"] if align_to_grid is None else align_to_grid
        raw = self._read_value(self._BAGS_KEY, "FFlags")
        try:
            flags = int(raw) if raw else 0x40000000  # a sane baseline default bag flag
        except (TypeError, ValueError):
            flags = 0x40000000
        flags = (flags | self._FFLAG_AUTO_ARRANGE) if new_auto else (flags & ~self._FFLAG_AUTO_ARRANGE)
        flags = (flags | self._FFLAG_ALIGN_TO_GRID) if new_grid else (flags & ~self._FFLAG_ALIGN_TO_GRID)
        result = self._write_dword(self._BAGS_KEY, "FFlags", flags)
        if "error" in result:
            return result
        self._refresh_desktop()
        return {
            "success": True,
            "auto_arrange": new_auto,
            "align_to_grid": new_grid,
            "note": "Restart Explorer (uictl_taskbar_restart_explorer) if the layout doesn't visibly update.",
        }
