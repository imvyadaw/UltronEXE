"""Font Manager
==============
Lists, installs, and removes fonts, and controls text-rendering
settings (ClearType/font smoothing, default UI font substitution) -
the same surface area as Settings > Personalization > Fonts.

Install/uninstall are done PER-USER (no admin needed), under
%LOCALAPPDATA%\\Microsoft\\Windows\\Fonts +
HKCU\\Software\\Microsoft\\Windows NT\\CurrentVersion\\Fonts - this is
the same mechanism Windows itself uses for "Install for me only" in
the Fonts settings page, distinct from a system-wide install under
C:\\Windows\\Fonts which needs admin and is intentionally NOT
implemented here to keep this module admin-free like its siblings.
System-wide fonts are still visible via list_installed_fonts (which
also reads the HKLM key, read-only).

Distinct from theme_manager.py/accent_color.py (color/mode, not
typography) and system_config/system_properties.py (general system
info, not fonts specifically).

Installing/listing fonts and toggling ClearType are cosmetic, not
confirm-gated. Uninstalling a font deletes a file, so it IS
confirm-gated. Changing the default UI font via FontSubstitutes can
make system text unreadable if given a bad value and needs sign-out to
fully apply, so it is also confirm-gated.
"""
import logging

import ctypes
import os
import shutil
import subprocess
from pathlib import Path
from typing import Dict, List, Optional


class FontManager:
    """Inspect, install, and remove fonts; control text-rendering settings."""

    _HKLM_FONTS_KEY = r"HKLM\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Fonts"
    _HKCU_FONTS_KEY = r"HKCU\Software\Microsoft\Windows NT\CurrentVersion\Fonts"
    _DESKTOP_KEY = r"HKCU\Control Panel\Desktop"
    _FONT_SUBSTITUTES_KEY = r"HKLM\SOFTWARE\Microsoft\Windows NT\CurrentVersion\FontSubstitutes"
    _FONT_EXTS = {".ttf", ".ttc", ".otf", ".fon"}

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

    def _list_fonts_key(self, key: str) -> List[Dict]:
        script = (
            f'Get-ItemProperty -Path "Registry::{key}" -ErrorAction SilentlyContinue | '
            "Get-Member -MemberType NoteProperty | Where-Object { $_.Name -notlike 'PS*' } | "
            "ForEach-Object { $_.Name }"
        )
        result = self._run_ps(script)
        if "error" in result or not result.get("success"):
            return []
        return [{"name": line.strip()} for line in result["stdout"].splitlines() if line.strip()]

    def _user_fonts_dir(self) -> Path:
        local_appdata = os.environ.get("LOCALAPPDATA", "")
        return Path(local_appdata) / "Microsoft" / "Windows" / "Fonts"

    def list_installed_fonts(self) -> Dict:
        """List installed fonts: system-wide (HKLM, read-only here) and
        per-user (HKCU, the ones this manager can also remove)."""
        system_fonts = self._list_fonts_key(self._HKLM_FONTS_KEY)
        user_fonts = self._list_fonts_key(self._HKCU_FONTS_KEY)
        return {
            "system_fonts": system_fonts,
            "system_count": len(system_fonts),
            "user_fonts": user_fonts,
            "user_count": len(user_fonts),
        }

    def install_font(self, font_path: str, confirm: bool = False) -> Dict:
        """Install a .ttf/.ttc/.otf/.fon file for the current user only
        (no admin needed) - copies it to the per-user Fonts folder,
        registers it via AddFontResource, and broadcasts WM_FONTCHANGE
        so running apps pick it up immediately. Not confirm-gated -
        adding a font is non-destructive."""
        src = Path(font_path).expanduser()
        if not src.exists():
            return {"error": f"Font file not found: {font_path}"}
        if src.suffix.lower() not in self._FONT_EXTS:
            return {"error": f"Unsupported font extension '{src.suffix}'. Expected one of {sorted(self._FONT_EXTS)}."}

        dest_dir = self._user_fonts_dir()
        try:
            dest_dir.mkdir(parents=True, exist_ok=True)
            dest = dest_dir / src.name
            shutil.copyfile(src, dest)
        except Exception as e:
            return {"error": f"Could not copy font into place: {e}"}

        try:
            added = ctypes.windll.gdi32.AddFontResourceW(str(dest))
            if not added:
                return {
                    "error": "Font file copied but Windows rejected it (AddFontResourceW failed) - it may be corrupt or an unsupported format."
                }
        except AttributeError:
            return {"error": "gdi32.AddFontResourceW is only available on Windows."}
        except Exception as e:
            return {"error": str(e)}

        font_name = f"{src.stem} (TrueType)"
        script = (
            f'New-Item -Path "Registry::{self._HKCU_FONTS_KEY}" -Force | Out-Null; '
            f'Set-ItemProperty -Path "Registry::{self._HKCU_FONTS_KEY}" -Name "{font_name}" -Value "{dest.name}" -Type String -Force'
        )
        self._run_ps(script)  # best-effort; the font already works this session even if this fails

        try:
            HWND_BROADCAST, WM_FONTCHANGE = 0xFFFF, 0x001D
            ctypes.windll.user32.SendMessageTimeoutW(HWND_BROADCAST, WM_FONTCHANGE, 0, 0, 0, 1000, None)
        except Exception:
            logging.getLogger(__name__).exception("Suppressed Exception")
        return {"success": True, "installed": str(dest), "font_name": font_name}

    def uninstall_font(self, font_name: str, confirm: bool = False) -> Dict:
        """Remove a per-user-installed font: deletes the registry entry
        and the underlying file. Confirm-gated - this deletes a file.
        Only removes fonts installed via install_font (per-user);
        system-wide fonts under C:\\Windows\\Fonts are untouched."""
        if not confirm:
            return {
                "error": "This deletes a font file. Call again with confirm=True to proceed.",
                "requires_confirmation": True,
            }

        script = f'(Get-ItemProperty -Path "Registry::{self._HKCU_FONTS_KEY}" -Name "{font_name}" -ErrorAction SilentlyContinue)."{font_name}"'
        result = self._run_ps(script)
        if "error" in result:
            return result
        filename = result.get("stdout", "").strip()
        if not filename:
            return {"error": f"No per-user font entry found named '{font_name}'."}

        del_script = f'Remove-ItemProperty -Path "Registry::{self._HKCU_FONTS_KEY}" -Name "{font_name}" -Force'
        del_result = self._run_ps(del_script)
        if "error" in del_result or not del_result.get("success"):
            return {"error": del_result.get("stderr") or "Failed to remove the registry entry."}

        font_file = self._user_fonts_dir() / filename
        try:
            if font_file.exists():
                try:
                    ctypes.windll.gdi32.RemoveFontResourceW(str(font_file))
                except Exception:
                    logging.getLogger(__name__).exception("Suppressed Exception")
                font_file.unlink()
        except Exception as e:
            return {
                "success": True,
                "removed_registry_entry": True,
                "warning": f"Registry entry removed but the font file could not be deleted: {e}",
            }
        return {"success": True, "removed": font_name}

    # -- Text rendering: ClearType / font smoothing --------------------------
    def get_font_smoothing(self) -> Dict:
        """Read whether font smoothing is on and which type
        (standard antialiasing vs ClearType)."""
        script = f'(Get-ItemProperty -Path "Registry::{self._DESKTOP_KEY}" -Name FontSmoothing -ErrorAction SilentlyContinue).FontSmoothing'
        result = self._run_ps(script)
        smoothing_on = result.get("success") and result.get("stdout", "").strip() == "2"
        script2 = f'(Get-ItemProperty -Path "Registry::{self._DESKTOP_KEY}" -Name FontSmoothingType -ErrorAction SilentlyContinue).FontSmoothingType'
        result2 = self._run_ps(script2)
        raw_type = result2.get("stdout", "").strip() if result2.get("success") else ""
        smoothing_type = "cleartype" if raw_type == "2" else ("standard" if raw_type == "1" else None)
        return {"font_smoothing_enabled": bool(smoothing_on), "font_smoothing_type": smoothing_type}

    def set_cleartype(self, enabled: bool, confirm: bool = False) -> Dict:
        """Turn ClearType text rendering on/off. Not confirm-gated -
        a per-user display preference, takes effect live."""
        script = (
            f'New-Item -Path "Registry::{self._DESKTOP_KEY}" -Force | Out-Null; '
            f'Set-ItemProperty -Path "Registry::{self._DESKTOP_KEY}" -Name FontSmoothing -Value 2 -Type String -Force; '
            f'Set-ItemProperty -Path "Registry::{self._DESKTOP_KEY}" -Name FontSmoothingType -Value {2 if enabled else 1} -Type DWord -Force'
        )
        result = self._run_ps(script)
        if "error" in result:
            return result
        if not result["success"]:
            return {"error": result["stderr"] or "Failed to set font smoothing."}
        try:
            SPI_SETFONTSMOOTHINGTYPE = 0x200B
            SPIF_SENDCHANGE = 0x2
            ctypes.windll.user32.SystemParametersInfoW(
                SPI_SETFONTSMOOTHINGTYPE, 0, 2 if enabled else 1, SPIF_SENDCHANGE
            )
        except Exception:
            logging.getLogger(__name__).exception("Suppressed Exception")
        return {"success": True, "cleartype_enabled": enabled}

    # -- Default UI font substitution -----------------------------------------
    def get_default_ui_font_substitute(self) -> Dict:
        """Read what 'Segoe UI' (the default Windows UI font) is
        currently substituted with, if anything."""
        script = f'(Get-ItemProperty -Path "Registry::{self._FONT_SUBSTITUTES_KEY}" -Name "Segoe UI" -ErrorAction SilentlyContinue)."Segoe UI"'
        result = self._run_ps(script)
        value = result.get("stdout", "").strip() if result.get("success") else ""
        return {"segoe_ui_substitute": value or None}

    def set_default_ui_font_substitute(self, font_name: Optional[str], confirm: bool = False) -> Dict:
        """Replace the system UI font by substituting 'Segoe UI' with
        another installed font (pass None to clear the substitution and
        restore the default). Needs admin (writes HKLM) and a sign-out
        to fully apply everywhere, and a bad/unavailable font name can
        make system text hard to read - confirm-gated."""
        if not confirm:
            return {
                "error": "Changing the system UI font needs admin rights, needs a sign-out to fully apply, and can hurt readability if the font is unsuitable. Call again with confirm=True to proceed.",
                "requires_confirmation": True,
            }
        if font_name is None:
            script = f'Remove-ItemProperty -Path "Registry::{self._FONT_SUBSTITUTES_KEY}" -Name "Segoe UI" -ErrorAction SilentlyContinue'
            result = self._run_ps(script)
            if "error" in result:
                return result
            return {
                "success": True,
                "segoe_ui_substitute": None,
                "note": "Sign out and back in for this to fully apply.",
            }
        script = (
            f'New-Item -Path "Registry::{self._FONT_SUBSTITUTES_KEY}" -Force | Out-Null; '
            f'Set-ItemProperty -Path "Registry::{self._FONT_SUBSTITUTES_KEY}" -Name "Segoe UI" -Value "{font_name}" -Type String -Force'
        )
        result = self._run_ps(script)
        if "error" in result:
            return result
        if not result["success"]:
            return {
                "error": result["stderr"]
                or "Failed to write the font substitution (needs admin - try running Ultron elevated)."
            }
        return {
            "success": True,
            "segoe_ui_substitute": font_name,
            "note": "Sign out and back in for this to fully apply.",
        }
