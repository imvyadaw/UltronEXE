"""Theme Manager
================
Reads and controls Windows' light/dark appearance mode and transparency
effects, plus listing/applying .theme files - the same settings under
Settings > Personalization > Colors and > Themes. Registry:
HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Themes\\Personalize
(AppsUseLightTheme, SystemUsesLightTheme, EnableTransparency - all
per-user, HKCU, no admin needed for any of it).

Distinct from accent_color.py (the accent color itself and where it's
shown) - this module is light/dark mode and transparency only. Distinct
from the top-level ui/ package (ULTRON's own interface theme, not
Windows').

Every setter here is a per-user cosmetic preference, not a security or
system-stability change, so these are NOT confirm-gated - same class
as any other UI-preference toggle. apply_theme launches an external
.theme file, which is a mechanical action, also not confirm-gated.
"""

import os
import subprocess
from pathlib import Path
from typing import Dict, List


class ThemeManager:
    """Inspect and control Windows light/dark mode, transparency, and .theme files."""

    _KEY = r"HKCU\Software\Microsoft\Windows\CurrentVersion\Themes\Personalize"

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

    def _read_dword(self, name: str) -> Dict:
        script = f'(Get-ItemProperty -Path "Registry::{self._KEY}" -Name {name} -ErrorAction SilentlyContinue).{name}'
        result = self._run_ps(script)
        if "error" in result:
            return result
        if not result["success"]:
            return {"error": result["stderr"] or f"Could not read {name}."}
        raw = result["stdout"]
        return {"value": int(raw) if raw.strip().isdigit() else None}

    def _write_dword(self, name: str, value: int) -> Dict:
        script = (
            f'New-Item -Path "Registry::{self._KEY}" -Force | Out-Null; '
            f'Set-ItemProperty -Path "Registry::{self._KEY}" -Name {name} -Value {value} -Type DWord -Force'
        )
        result = self._run_ps(script)
        if "error" in result:
            return result
        if not result["success"]:
            return {"error": result["stderr"] or f"Failed to set {name}."}
        return {"success": True}

    def get_status(self) -> Dict:
        """Read whether apps use light mode, whether system UI (taskbar,
        Start, action center) uses light mode, and whether transparency
        effects are on."""
        apps = self._read_dword("AppsUseLightTheme")
        system = self._read_dword("SystemUsesLightTheme")
        transparency = self._read_dword("EnableTransparency")
        return {
            "apps_theme": "light" if apps.get("value") == 1 else ("dark" if apps.get("value") == 0 else None),
            "system_theme": "light" if system.get("value") == 1 else ("dark" if system.get("value") == 0 else None),
            "transparency_enabled": bool(transparency.get("value")) if transparency.get("value") is not None else None,
        }

    def set_app_mode(self, dark: bool, confirm: bool = False) -> Dict:
        """Set whether apps (Settings, File Explorer, most Store apps)
        render in dark or light mode. Some apps need a restart to pick
        it up. Not confirm-gated - a per-user cosmetic preference."""
        result = self._write_dword("AppsUseLightTheme", 0 if dark else 1)
        if "error" in result:
            return result
        return {
            "success": True,
            "apps_theme": "dark" if dark else "light",
            "note": "Some open apps need to be restarted to pick this up.",
        }

    def set_system_mode(self, dark: bool, confirm: bool = False) -> Dict:
        """Set whether system UI surfaces (taskbar, Start menu, action
        center) render in dark or light mode. Not confirm-gated."""
        result = self._write_dword("SystemUsesLightTheme", 0 if dark else 1)
        if "error" in result:
            return result
        return {"success": True, "system_theme": "dark" if dark else "light"}

    def set_mode(self, dark: bool, confirm: bool = False) -> Dict:
        """Convenience: set both apps and system UI to the same dark/light
        mode in one call. Not confirm-gated."""
        apps = self.set_app_mode(dark)
        if "error" in apps:
            return apps
        system = self.set_system_mode(dark)
        if "error" in system:
            return system
        return {"success": True, "mode": "dark" if dark else "light"}

    def set_transparency(self, enabled: bool, confirm: bool = False) -> Dict:
        """Turn transparency/blur effects (Start, taskbar, action center)
        on or off. Not confirm-gated."""
        result = self._write_dword("EnableTransparency", 1 if enabled else 0)
        if "error" in result:
            return result
        return {"success": True, "transparency_enabled": enabled}

    def list_installed_themes(self) -> Dict:
        """List available .theme files: the built-in Windows themes plus
        any the user has saved/synced. No admin needed."""
        search_dirs = [
            Path(r"C:\Windows\Resources\Themes"),
            Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "Windows" / "Themes",
        ]
        themes: List[Dict] = []
        for d in search_dirs:
            if d.exists():
                for f in d.glob("*.theme"):
                    themes.append({"name": f.stem, "path": str(f)})
        return {"themes": themes, "count": len(themes)}

    def apply_theme(self, theme_path: str) -> Dict:
        """Apply a .theme file by launching it - Windows applies it and
        switches focus to Personalization settings, same as double-
        clicking it in Explorer. Not confirm-gated - purely cosmetic."""
        p = Path(theme_path).expanduser()
        if not p.exists():
            return {"error": f".theme file not found: {theme_path}"}
        try:
            os.startfile(str(p))  # noqa: this module is Windows-only by design
            return {"success": True, "applied": str(p)}
        except AttributeError:
            return {"error": "os.startfile is only available on Windows."}
        except Exception as e:
            return {"error": str(e)}
