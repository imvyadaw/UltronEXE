"""Accent Color Manager
=======================
Reads and controls the Windows accent color and where it's shown - the
same settings under Settings > Personalization > Colors. Two registry
locations, both HKCU, no admin needed:
  - HKCU\\Software\\Microsoft\\Windows\\DWM: AccentColor / ColorizationColor
    (the actual ABGR color values DWM uses for window borders/title bars).
  - HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Themes\\Personalize:
    AutoColorization (pick accent from wallpaper) and ColorPrevalence
    (show accent on Start/taskbar/action center).

Distinct from theme_manager.py (light/dark mode, transparency) - this
module is the accent color itself and its automatic/manual/prevalence
settings only.

All per-user cosmetic preferences - none of these are confirm-gated,
same class as any other UI-preference toggle.
"""

import subprocess
from typing import Dict, Optional


class AccentColorManager:
    """Inspect and control the Windows accent color and where it's applied."""

    _DWM_KEY = r"HKCU\Software\Microsoft\Windows\DWM"
    _PERSONALIZE_KEY = r"HKCU\Software\Microsoft\Windows\CurrentVersion\Themes\Personalize"

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

    def _read_dword(self, key: str, name: str) -> Optional[int]:
        script = f'(Get-ItemProperty -Path "Registry::{key}" -Name {name} -ErrorAction SilentlyContinue).{name}'
        result = self._run_ps(script)
        if "error" in result or not result.get("success"):
            return None
        raw = result["stdout"].strip()
        try:
            return int(raw)
        except (ValueError, TypeError):
            return None

    def _write_dword(self, key: str, name: str, value: int) -> Dict:
        script = (
            f'New-Item -Path "Registry::{key}" -Force | Out-Null; '
            f'Set-ItemProperty -Path "Registry::{key}" -Name {name} -Value {value} -Type DWord -Force'
        )
        result = self._run_ps(script)
        if "error" in result:
            return result
        if not result["success"]:
            return {"error": result["stderr"] or f"Failed to set {name}."}
        return {"success": True}

    @staticmethod
    def _hex_to_abgr_dword(hex_color: str) -> Optional[int]:
        """Convert a '#RRGGBB' or 'RRGGBB' string to the ABGR-ordered
        DWORD Windows stores AccentColor as (opaque, alpha=0xFF)."""
        h = hex_color.strip().lstrip("#")
        if len(h) != 6 or any(c not in "0123456789abcdefABCDEF" for c in h):
            return None
        r, g, b = h[0:2], h[2:4], h[4:6]
        return int(f"FF{b}{g}{r}", 16)

    @staticmethod
    def _abgr_dword_to_hex(value: int) -> str:
        b = (value >> 0) & 0xFF
        g = (value >> 8) & 0xFF
        r = (value >> 16) & 0xFF
        return f"#{r:02X}{g:02X}{b:02X}"

    def get_accent_color(self) -> Dict:
        """Read the current accent color as a '#RRGGBB' hex string."""
        value = self._read_dword(self._DWM_KEY, "AccentColor")
        if value is None:
            return {"error": "Could not read AccentColor - it may not be set yet."}
        return {"accent_color": self._abgr_dword_to_hex(value)}

    def set_accent_color(self, hex_color: str, confirm: bool = False) -> Dict:
        """Set a specific accent color from a '#RRGGBB' hex string.
        Writes both AccentColor and ColorizationColor for DWM to pick
        up. Automatically turns off 'auto pick from background' since
        that would otherwise overwrite a manual choice. Not confirm-
        gated - a per-user cosmetic preference."""
        dword = self._hex_to_abgr_dword(hex_color)
        if dword is None:
            return {"error": "hex_color must look like '#RRGGBB' or 'RRGGBB'."}
        self.set_auto_from_background(False)
        r1 = self._write_dword(self._DWM_KEY, "AccentColor", dword)
        if "error" in r1:
            return r1
        r2 = self._write_dword(self._DWM_KEY, "ColorizationColor", dword)
        if "error" in r2:
            return r2
        return {"success": True, "accent_color": hex_color if hex_color.startswith("#") else f"#{hex_color}"}

    def get_auto_from_background(self) -> Dict:
        """Read whether Windows picks the accent color automatically
        from the desktop wallpaper (AutoColorization)."""
        value = self._read_dword(self._PERSONALIZE_KEY, "AutoColorization")
        return {"auto_from_background": bool(value) if value is not None else False}

    def set_auto_from_background(self, enabled: bool, confirm: bool = False) -> Dict:
        """Turn 'automatically pick an accent color from my background'
        on or off. Not confirm-gated."""
        result = self._write_dword(self._PERSONALIZE_KEY, "AutoColorization", 1 if enabled else 0)
        if "error" in result:
            return result
        return {"success": True, "auto_from_background": enabled}

    def get_color_prevalence(self) -> Dict:
        """Read whether the accent color is shown on Start, taskbar, and
        action center (ColorPrevalence)."""
        value = self._read_dword(self._PERSONALIZE_KEY, "ColorPrevalence")
        return {"color_prevalence_enabled": bool(value) if value is not None else False}

    def set_color_prevalence(self, enabled: bool, confirm: bool = False) -> Dict:
        """Turn 'show accent color on Start, taskbar, and action center'
        on or off. Not confirm-gated."""
        result = self._write_dword(self._PERSONALIZE_KEY, "ColorPrevalence", 1 if enabled else 0)
        if "error" in result:
            return result
        return {"success": True, "color_prevalence_enabled": enabled}

    def get_title_bar_prevalence(self) -> Dict:
        """Read whether the accent color is shown on window title bars
        and borders (ColorPrevalence under the DWM key - separate flag
        from the Start/taskbar one above)."""
        value = self._read_dword(self._DWM_KEY, "ColorPrevalence")
        return {"title_bar_color_prevalence_enabled": bool(value) if value is not None else False}

    def set_title_bar_prevalence(self, enabled: bool, confirm: bool = False) -> Dict:
        """Turn 'show accent color on title bars and window borders' on
        or off. Not confirm-gated."""
        result = self._write_dword(self._DWM_KEY, "ColorPrevalence", 1 if enabled else 0)
        if "error" in result:
            return result
        return {"success": True, "title_bar_color_prevalence_enabled": enabled}
