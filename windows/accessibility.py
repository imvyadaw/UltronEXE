"""Accessibility tools
===================
Toggle Windows accessibility features: Narrator (screen reader), high
contrast mode, Magnifier, and Sticky Keys, plus a quick spoken-style
announcement helper that reuses the assistant's own TTS voice
(voice/tts) rather than Narrator, for cases where Ultron just wants to
say something out loud without switching the OS's screen reader on.
"""

import ctypes
import subprocess
from typing import Dict

# SystemParametersInfo constants for toggling accessibility features via the
# Win32 API (more reliable than simulating the keyboard shortcuts, which
# vary/are sometimes disabled by group policy).
SPI_SETHIGHCONTRAST = 0x0043
SPI_SETSTICKYKEYS = 0x003B
SPI_SETTOGGLEKEYS = 0x0035
HCF_HIGHCONTRASTON = 0x00000001


class AccessibilityTools:
    """Toggle Windows accessibility features."""

    def toggle_narrator(self) -> Dict:
        """Toggle Windows Narrator (screen reader) on/off. Narrator has no
        stable public API to *query* its state, so this just launches/kills
        the process - calling it twice turns it off again."""
        try:
            result = subprocess.run(
                ["tasklist", "/FI", "IMAGENAME eq Narrator.exe"], capture_output=True, text=True, timeout=10
            )
            running = "Narrator.exe" in result.stdout
            if running:
                subprocess.run(["taskkill", "/IM", "Narrator.exe", "/F"], check=False, timeout=10)
                return {"success": True, "narrator": "stopped"}
            subprocess.Popen(["Narrator.exe"])
            return {"success": True, "narrator": "started"}
        except Exception as e:
            return {"error": str(e)}

    def set_high_contrast(self, enabled: bool) -> Dict:
        """Turn Windows High Contrast mode on or off."""
        try:

            class HIGHCONTRAST(ctypes.Structure):
                _fields_ = [
                    ("cbSize", ctypes.c_uint),
                    ("dwFlags", ctypes.c_uint),
                    ("lpszDefaultScheme", ctypes.c_wchar_p),
                ]

            hc = HIGHCONTRAST()
            hc.cbSize = ctypes.sizeof(HIGHCONTRAST)
            hc.dwFlags = HCF_HIGHCONTRASTON if enabled else 0
            hc.lpszDefaultScheme = None
            ctypes.windll.user32.SystemParametersInfoW(
                SPI_SETHIGHCONTRAST, ctypes.sizeof(HIGHCONTRAST), ctypes.byref(hc), 0
            )
            return {"success": True, "high_contrast": enabled}
        except Exception as e:
            return {"error": str(e)}

    def toggle_magnifier(self) -> Dict:
        """Toggle Windows Magnifier on/off."""
        try:
            result = subprocess.run(
                ["tasklist", "/FI", "IMAGENAME eq Magnify.exe"], capture_output=True, text=True, timeout=10
            )
            running = "Magnify.exe" in result.stdout
            if running:
                subprocess.run(["taskkill", "/IM", "Magnify.exe", "/F"], check=False, timeout=10)
                return {"success": True, "magnifier": "stopped"}
            subprocess.Popen(["magnify.exe"])
            return {"success": True, "magnifier": "started"}
        except Exception as e:
            return {"error": str(e)}

    def set_sticky_keys(self, enabled: bool) -> Dict:
        """Turn Sticky Keys (press modifier keys one at a time instead of
        holding them) on or off."""
        try:

            class STICKYKEYS(ctypes.Structure):
                _fields_ = [("cbSize", ctypes.c_uint), ("dwFlags", ctypes.c_uint)]

            SKF_STICKYKEYSON = 0x00000001
            sk = STICKYKEYS()
            sk.cbSize = ctypes.sizeof(STICKYKEYS)
            sk.dwFlags = SKF_STICKYKEYSON if enabled else 0
            ctypes.windll.user32.SystemParametersInfoW(
                SPI_SETSTICKYKEYS, ctypes.sizeof(STICKYKEYS), ctypes.byref(sk), 0
            )
            return {"success": True, "sticky_keys": enabled}
        except Exception as e:
            return {"error": str(e)}

    def set_cursor_size(self, size: int) -> Dict:
        """Set the mouse cursor size via the registry (1 = default, up to 15 = largest).
        Takes effect after a sign-out/sign-in in most Windows versions."""
        if not 1 <= size <= 15:
            return {"error": "size must be between 1 and 15"}
        try:
            import winreg

            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Control Panel\Cursors", 0, winreg.KEY_SET_VALUE) as key:
                winreg.SetValueEx(key, "CursorBaseSize", 0, winreg.REG_SZ, str(size * 8))
            return {"success": True, "cursor_size": size, "note": "May require sign-out/sign-in to fully apply"}
        except Exception as e:
            return {"error": str(e)}

    def announce(self, text: str) -> Dict:
        """Speak `text` out loud immediately using the assistant's own TTS
        voice (not Narrator) - a lightweight way to surface an accessibility
        announcement without toggling the OS screen reader on."""
        try:
            from voice.tts.tts_engine import speak

            speak(text)
            return {"success": True, "announced": text}
        except Exception as e:
            return {"error": f"Could not use voice/tts engine: {e}"}
