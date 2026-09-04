"""Cursor Manager
================
Reads and controls the Windows mouse pointer - scheme, per-cursor
files, speed/acceleration, trails, snap-to-default-button, and the
Windows 11 accessibility pointer size/color - the same settings under
Settings > Bluetooth & devices > Mouse and Settings > Accessibility >
Mouse pointer and touch, plus the classic Control Panel > Mouse >
Pointers tab. Registry, all HKCU, no admin needed:
  - HKCU\\Control Panel\\Cursors: (Default) = active scheme name, plus
    one value per cursor role (Arrow, Help, AppStarting, Wait,
    Crosshair, IBeam, NWPen, No, SizeNS, SizeWE, SizeNWSE, SizeNESW,
    SizeAll, UpArrow, Hand) holding a .cur/.ani path.
  - HKCU\\Control Panel\\Cursors\\Schemes: named schemes, each a
    pipe-delimited list of the 15 paths above in the same order.
  - HKCU\\Control Panel\\Mouse: MouseSensitivity (1-20 pointer speed),
    MouseSpeed ('1'/'0' - Enhance pointer precision), MouseTrails
    ('0' off, else trail length), SnapToDefaultButton ('1'/'0').
  - HKCU\\Software\\Microsoft\\Accessibility: CursorBaseSize (DWORD,
    default 32, larger = bigger pointer) and CursorColor (DWORD,
    0x00BBGGRR - same channel order as accent_color.py's AccentColor).

Distinct from theme_manager.py/accent_color.py (desktop/window
chrome, not the pointer itself) and from automation/mouse/mouse.py
(moving/clicking the cursor programmatically, not its appearance or
tracking settings).

Every setter here is a per-user cosmetic/input preference, same class
as theme_manager.py's toggles, so none of these are confirm-gated.
Scheme/size/color changes call SPI_SETCURSORS so the new pointer(s)
show up immediately without sign-out.
"""

import ctypes
import subprocess
from typing import Dict, Optional

_CURSOR_ROLES = [
    "Arrow",
    "Help",
    "AppStarting",
    "Wait",
    "Crosshair",
    "IBeam",
    "NWPen",
    "No",
    "SizeNS",
    "SizeWE",
    "SizeNWSE",
    "SizeNESW",
    "SizeAll",
    "UpArrow",
    "Hand",
]


class CursorManager:
    """Inspect and control the Windows mouse pointer scheme, speed, and appearance."""

    _CURSORS_KEY = r"HKCU\Control Panel\Cursors"
    _SCHEMES_KEY = r"HKCU\Control Panel\Cursors\Schemes"
    _MOUSE_KEY = r"HKCU\Control Panel\Mouse"
    _ACCESSIBILITY_KEY = r"HKCU\Software\Microsoft\Accessibility"

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

    def _read_string(self, key: str, name: str) -> Optional[str]:
        script = f"(Get-ItemProperty -Path \"Registry::{key}\" -Name '{name}' -ErrorAction SilentlyContinue).'{name}'"
        result = self._run_ps(script)
        if "error" in result or not result.get("success"):
            return None
        raw = result["stdout"].strip()
        return raw or None

    def _write_string(self, key: str, name: str, value: str) -> Dict:
        escaped = value.replace("'", "''")
        script = (
            f'New-Item -Path "Registry::{key}" -Force | Out-Null; '
            f"Set-ItemProperty -Path \"Registry::{key}\" -Name '{name}' -Value '{escaped}' -Type String -Force"
        )
        result = self._run_ps(script)
        if "error" in result:
            return result
        if not result["success"]:
            return {"error": result["stderr"] or f"Failed to set {name}."}
        return {"success": True}

    def _read_dword(self, key: str, name: str) -> Optional[int]:
        script = f"(Get-ItemProperty -Path \"Registry::{key}\" -Name '{name}' -ErrorAction SilentlyContinue).'{name}'"
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
            f"Set-ItemProperty -Path \"Registry::{key}\" -Name '{name}' -Value {value} -Type DWord -Force"
        )
        result = self._run_ps(script)
        if "error" in result:
            return result
        if not result["success"]:
            return {"error": result["stderr"] or f"Failed to set {name}."}
        return {"success": True}

    def _apply_cursors(self) -> None:
        """Broadcast SPI_SETCURSORS so the active scheme/size/color reloads now."""
        try:
            SPI_SETCURSORS = 0x0057
            SPIF_UPDATEINIFILE, SPIF_SENDCHANGE = 0x01, 0x02
            ctypes.windll.user32.SystemParametersInfoW(SPI_SETCURSORS, 0, None, SPIF_UPDATEINIFILE | SPIF_SENDCHANGE)
        except Exception:
            pass  # best-effort - non-Windows or restricted environment

    def get_scheme(self) -> Dict:
        """Read the active cursor scheme name."""
        name = self._read_string(self._CURSORS_KEY, "")
        return {"scheme": name}

    def list_schemes(self) -> Dict:
        """List cursor scheme names available under Cursors\\Schemes,
        both built-in (e.g. 'Windows Default', 'Windows Black') and
        any the user has saved."""
        script = f'(Get-Item -Path "Registry::{self._SCHEMES_KEY}" -ErrorAction SilentlyContinue).GetValueNames()'
        result = self._run_ps(script)
        if "error" in result:
            return result
        if not result["success"]:
            return {"error": result["stderr"] or "Could not list cursor schemes."}
        names = [n for n in result["stdout"].splitlines() if n.strip()]
        return {"schemes": names, "count": len(names)}

    def set_scheme(self, scheme_name: str) -> Dict:
        """Switch to a named cursor scheme - copies its 15 cursor paths
        from Cursors\\Schemes into the active Cursors values, then
        applies immediately. Not confirm-gated - a cosmetic preference."""
        script = f"(Get-ItemProperty -Path \"Registry::{self._SCHEMES_KEY}\" -Name '{scheme_name}' -ErrorAction SilentlyContinue).'{scheme_name}'"
        result = self._run_ps(script)
        if "error" in result:
            return result
        if not result["success"] or not result["stdout"].strip():
            return {"error": f"Cursor scheme '{scheme_name}' not found."}
        paths = result["stdout"].strip().split(",")
        if len(paths) != len(_CURSOR_ROLES):
            return {"error": f"Scheme '{scheme_name}' has an unexpected number of cursors ({len(paths)})."}
        for role, path in zip(_CURSOR_ROLES, paths):
            r = self._write_string(self._CURSORS_KEY, role, path)
            if "error" in r:
                return r
        self._write_string(self._CURSORS_KEY, "", scheme_name)
        self._apply_cursors()
        return {"success": True, "scheme": scheme_name}

    def set_cursor(self, role: str, cursor_path: str) -> Dict:
        """Set a single cursor role (e.g. 'Arrow', 'Hand', 'IBeam') to a
        specific .cur/.ani file, without switching the whole scheme.
        This turns the active scheme into '(None)' (a custom mix), same
        as doing it from Control Panel. Not confirm-gated."""
        if role not in _CURSOR_ROLES:
            return {"error": f"Unknown cursor role '{role}'. Valid roles: {_CURSOR_ROLES}"}
        result = self._write_string(self._CURSORS_KEY, role, cursor_path)
        if "error" in result:
            return result
        self._write_string(self._CURSORS_KEY, "", "")
        self._apply_cursors()
        return {"success": True, "role": role, "cursor_path": cursor_path}

    def get_pointer_speed(self) -> Dict:
        """Read pointer speed (1-20) and whether 'Enhance pointer precision' is on."""
        speed = self._read_dword(self._MOUSE_KEY, "MouseSensitivity")
        precision = self._read_string(self._MOUSE_KEY, "MouseSpeed")
        return {
            "pointer_speed": speed,
            "enhance_pointer_precision": precision == "1" if precision is not None else None,
        }

    def set_pointer_speed(self, speed: int) -> Dict:
        """Set pointer speed, 1 (slowest) to 20 (fastest, default 10). Not confirm-gated."""
        if not 1 <= speed <= 20:
            return {"error": "speed must be between 1 and 20."}
        result = self._write_dword(self._MOUSE_KEY, "MouseSensitivity", speed)
        if "error" in result:
            return result
        return {"success": True, "pointer_speed": speed}

    def set_enhance_pointer_precision(self, enabled: bool) -> Dict:
        """Turn 'Enhance pointer precision' (pointer acceleration) on/off.
        Also sets the two acceleration threshold values Windows expects
        alongside it. Not confirm-gated."""
        r1 = self._write_string(self._MOUSE_KEY, "MouseSpeed", "1" if enabled else "0")
        if "error" in r1:
            return r1
        r2 = self._write_string(self._MOUSE_KEY, "MouseThreshold1", "6" if enabled else "0")
        r3 = self._write_string(self._MOUSE_KEY, "MouseThreshold2", "10" if enabled else "0")
        if "error" in r2:
            return r2
        if "error" in r3:
            return r3
        return {"success": True, "enhance_pointer_precision": enabled}

    def get_pointer_trails(self) -> Dict:
        """Read whether pointer trails are on and, if so, how long."""
        raw = self._read_string(self._MOUSE_KEY, "MouseTrails")
        try:
            length = int(raw) if raw is not None else 0
        except ValueError:
            length = 0
        return {"trails_enabled": length > 1, "trail_length": length if length > 1 else 0}

    def set_pointer_trails(self, enabled: bool, length: int = 5) -> Dict:
        """Turn pointer trails on/off; length (2-10) sets how long the
        trail is when enabled. Not confirm-gated."""
        if enabled and not 2 <= length <= 10:
            return {"error": "length must be between 2 and 10."}
        result = self._write_string(self._MOUSE_KEY, "MouseTrails", str(length) if enabled else "0")
        if "error" in result:
            return result
        return {"success": True, "trails_enabled": enabled, "trail_length": length if enabled else 0}

    def get_snap_to_default_button(self) -> Dict:
        """Read whether the pointer automatically snaps to a dialog's default button."""
        raw = self._read_string(self._MOUSE_KEY, "SnapToDefaultButton")
        return {"snap_to_default_button": raw == "1"}

    def set_snap_to_default_button(self, enabled: bool) -> Dict:
        """Turn 'Automatically move pointer to the default button in a
        dialog box' on/off. Not confirm-gated."""
        result = self._write_string(self._MOUSE_KEY, "SnapToDefaultButton", "1" if enabled else "0")
        if "error" in result:
            return result
        return {"success": True, "snap_to_default_button": enabled}

    def get_pointer_size(self) -> Dict:
        """Read the accessibility pointer size in pixels (default 32)."""
        size = self._read_dword(self._ACCESSIBILITY_KEY, "CursorBaseSize")
        return {"pointer_size_px": size if size is not None else 32}

    def set_pointer_size(self, size_px: int) -> Dict:
        """Set the accessibility pointer size in pixels (32 = default,
        up to roughly 256 = largest). Not confirm-gated."""
        if not 32 <= size_px <= 256:
            return {"error": "size_px must be between 32 (default) and 256."}
        result = self._write_dword(self._ACCESSIBILITY_KEY, "CursorBaseSize", size_px)
        if "error" in result:
            return result
        self._apply_cursors()
        return {"success": True, "pointer_size_px": size_px}

    def get_pointer_color(self) -> Dict:
        """Read the accessibility pointer color as a '#RRGGBB' hex string,
        or None if using the default white/black system pointer."""
        value = self._read_dword(self._ACCESSIBILITY_KEY, "CursorColor")
        if value is None:
            return {"pointer_color": None}
        r, g, b = value & 0xFF, (value >> 8) & 0xFF, (value >> 16) & 0xFF
        return {"pointer_color": f"#{r:02X}{g:02X}{b:02X}"}

    def set_pointer_color(self, hex_color: str) -> Dict:
        """Set a custom accessibility pointer color from '#RRGGBB'.
        Not confirm-gated."""
        h = hex_color.strip().lstrip("#")
        if len(h) != 6 or any(c not in "0123456789abcdefABCDEF" for c in h):
            return {"error": "hex_color must look like '#RRGGBB' or 'RRGGBB'."}
        r, g, b = h[0:2], h[2:4], h[4:6]
        dword = int(f"00{b}{g}{r}", 16)
        result = self._write_dword(self._ACCESSIBILITY_KEY, "CursorColor", dword)
        if "error" in result:
            return result
        self._apply_cursors()
        return {"success": True, "pointer_color": f"#{hex_color.lstrip('#').upper()}"}
