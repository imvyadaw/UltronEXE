"""Widgets Manager
==================
Controls the Windows 11 Widgets board (news/weather/interests panel)
itself - opening/closing it, whether it auto-opens on taskbar hover,
and disabling the whole feature at the policy level. Distinct from
taskbar_manager.py's set_widgets_visible(), which only shows/hides the
Widgets ICON on the taskbar - the feature and its process can still be
running underneath even with the icon hidden; this module is the
board's own behavior and its all-up kill switch.
  - HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Feeds:
    ShellFeedsTaskbarOpenOnHover (DWORD, 1 = board opens just by
    hovering the taskbar icon, 0 = click required) - no admin needed.
  - HKLM\\SOFTWARE\\Policies\\Microsoft\\Dsh: AllowNewsAndInterests
    (DWORD, 0 = Widgets disabled machine-wide and the icon/process
    won't load at all, 1/absent = allowed) - the same Group Policy
    ("Allow news and interests") IT admins use; needs admin.

Opening/closing the board and the hover-open preference are cosmetic/
mechanical and are NOT confirm-gated. Disabling Widgets machine-wide
via policy IS confirm-gated - it needs admin, needs sign-out/`gpupdate`
to fully apply, and affects every user on the machine, not just the
current one.
"""

import subprocess
from typing import Dict, Optional


class WidgetsManager:
    """Inspect and control the Windows 11 Widgets board and its availability."""

    _FEEDS_KEY = r"HKCU\Software\Microsoft\Windows\CurrentVersion\Feeds"
    _POLICY_KEY = r"HKLM\SOFTWARE\Policies\Microsoft\Dsh"

    def _run(self, cmd: list, timeout: float = 15.0) -> Dict:
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
            return {
                "success": result.returncode == 0,
                "stdout": result.stdout.strip(),
                "stderr": result.stderr.strip(),
            }
        except FileNotFoundError:
            return {"error": f"{cmd[0]} not found - this is only available on Windows"}
        except subprocess.TimeoutExpired:
            return {"error": "Command timed out"}
        except Exception as e:
            return {"error": str(e)}

    def _run_ps(self, script: str, timeout: float = 15.0) -> Dict:
        return self._run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script], timeout)

    def _admin_hint(self, err: str) -> str:
        if err and ("denied" in err.lower() or "not authorized" in err.lower() or "elevat" in err.lower()):
            return err + " - this needs ULTRON running as Administrator."
        return err

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
            return {"error": self._admin_hint(result["stderr"] or f"Failed to set {name}.")}
        return {"success": True}

    def open_widgets_board(self) -> Dict:
        """Open the Widgets board, same as clicking its taskbar icon or
        pressing Win+W. Not confirm-gated."""
        result = self._run(["explorer.exe", "widgets:"])
        if "error" in result:
            return result
        return {"success": True, "opened": True}

    def close_widgets_board(self) -> Dict:
        """Close the Widgets board if it's open, by ending its host
        process. Not confirm-gated - just closes a window, doesn't
        disable the feature."""
        result = self._run(["taskkill", "/IM", "Widgets.exe", "/F"])
        if "error" in result:
            return result
        if not result["success"] and "not found" not in (result["stderr"] or "").lower():
            return {"error": result["stderr"] or "Could not close the Widgets board."}
        return {"success": True, "closed": True}

    def get_open_on_hover(self) -> Dict:
        """Read whether hovering the taskbar Widgets icon opens the
        board automatically (vs. requiring a click)."""
        value = self._read_dword(self._FEEDS_KEY, "ShellFeedsTaskbarOpenOnHover")
        return {"open_on_hover": bool(value) if value is not None else True}

    def set_open_on_hover(self, enabled: bool) -> Dict:
        """Turn 'open Widgets by hovering the taskbar icon' on/off (off
        means a click is required instead). Not confirm-gated."""
        result = self._write_dword(self._FEEDS_KEY, "ShellFeedsTaskbarOpenOnHover", 1 if enabled else 0)
        if "error" in result:
            return result
        return {"success": True, "open_on_hover": enabled}

    def get_widgets_allowed(self) -> Dict:
        """Read whether the Widgets feature is allowed machine-wide by
        policy (distinct from the taskbar icon being hidden)."""
        value = self._read_dword(self._POLICY_KEY, "AllowNewsAndInterests")
        return {"widgets_allowed": bool(value) if value is not None else True}

    def set_widgets_allowed(self, allowed: bool, confirm: bool = False) -> Dict:
        """Allow or fully disable the Widgets feature machine-wide via
        Group Policy (when disabled, the icon and background process
        won't load for ANY user, unlike taskbar_manager's icon-only
        toggle). Confirm-gated - needs admin, needs sign-out (or
        `gpupdate /force`) to fully apply, and affects every user."""
        if not confirm:
            return {
                "requires_confirmation": True,
                "preview": (
                    f"This will {'allow' if allowed else 'DISABLE'} Widgets for every user on this machine "
                    "(needs admin; a sign-out or gpupdate /force may be needed to fully apply)."
                ),
            }
        result = self._write_dword(self._POLICY_KEY, "AllowNewsAndInterests", 1 if allowed else 0)
        if "error" in result:
            return result
        return {
            "success": True,
            "widgets_allowed": allowed,
            "note": "Sign out (or run gpupdate /force) to fully apply.",
        }
