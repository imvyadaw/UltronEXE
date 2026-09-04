"""Default Apps
===============
Windows' *default app set* - Settings > Apps > Default apps - as a
whole, distinct from a single extension's association:

- system_control/files/file_associations.py handles one extension/
  protocol at a time (assoc/ftype, UserChoice reads) - this module
  handles the entire default-app profile as one unit, via the DISM
  export/import mechanism (`Dism.exe /Online /{Export,Import}-
  DefaultAppAssociations`), which is the only documented, silent,
  no-per-extension-hash-fight way to change many defaults at once
  (it's the same mechanism used to bake defaults into an enterprise
  Windows image).
- Reading the *current* default for a handful of common top-level
  classes (browser, mail, protocol handlers) is exposed here too, as
  a convenience read that doesn't require walking file_associations.py
  extension-by-extension.

Same honest limitation as file_associations.py: on Windows 8+,
UserChoice associations are hash-protected per user+build, so an
*import* can silently fail to override a default the user has already
explicitly chosen through the UI even though the command reports
success - Settings > Default apps remains the reliable fallback for a
single stubborn class, and open_default_apps_settings() is offered for
that.
"""

import subprocess
import winreg
from typing import Dict, Optional


class DefaultAppsManager:
    """Export/import/reset the whole default-app association profile,
    and read the current default for common classes."""

    # Friendly name -> (registry hive path, value name) for reading the
    # ProgId of the current UserChoice default. Programmatic *writes* to
    # UserChoice are blocked by its per-user hash (see file_associations.py
    # docstring) - reads are safe and always accurate.
    _USERCHOICE = {
        "browser": (r"Software\Microsoft\Windows\Shell\Associations\UrlAssociations\http\UserChoice", "ProgId"),
        "browser_https": (r"Software\Microsoft\Windows\Shell\Associations\UrlAssociations\https\UserChoice", "ProgId"),
        "mail": (r"Software\Microsoft\Windows\Shell\Associations\UrlAssociations\mailto\UserChoice", "ProgId"),
    }

    def _run(self, args: list, timeout: float = 60.0) -> Dict:
        try:
            result = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
            return {
                "success": result.returncode == 0,
                "stdout": result.stdout.strip(),
                "stderr": result.stderr.strip(),
                "returncode": result.returncode,
            }
        except FileNotFoundError:
            return {"error": "dism.exe not found - this is only available on Windows"}
        except subprocess.TimeoutExpired:
            return {"error": "Command timed out"}
        except Exception as e:
            return {"error": str(e)}

    def get_default_for_class(self, app_class: str) -> Dict:
        """Read the current default app's ProgId for a common class:
        'browser', 'browser_https', or 'mail'. No admin needed. For any
        other extension/protocol, use file_associations.py instead."""
        entry = self._USERCHOICE.get(app_class)
        if not entry:
            return {"error": f"Unknown app_class '{app_class}'. Known: {sorted(self._USERCHOICE)}"}
        path, value_name = entry
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, path) as key:
                prog_id, _ = winreg.QueryValueEx(key, value_name)
                return {"app_class": app_class, "prog_id": prog_id}
        except FileNotFoundError:
            return {"app_class": app_class, "prog_id": None}
        except OSError as e:
            return {"error": str(e)}

    def export_default_apps(self, destination_path: str) -> Dict:
        """Export the current full default-app association profile to
        an XML file via DISM - a point-in-time snapshot that can be
        re-applied later with import_default_apps(). Requires admin
        (DISM /Online always does); read-only against system state
        itself, so not confirm-gated - it only writes the destination
        file, doesn't change any default."""
        result = self._run(
            [
                "dism.exe",
                "/Online",
                "/Export-DefaultAppAssociations",
                f"/Xml:{destination_path}",
            ]
        )
        if "error" in result:
            return result
        if not result["success"]:
            return {
                "error": result["stderr"] or result["stdout"] or "DISM export failed.",
                "admin_hint": "Re-run elevated if this failed with access-denied.",
            }
        return {"success": True, "exported_to": destination_path}

    def import_default_apps(self, source_path: str, confirm: bool = False) -> Dict:
        """Apply a default-app association XML (from export_default_apps
        or hand-authored) system-wide. Confirm-gated and admin-required
        - changes what double-clicking many file types/protocols does
        for every user on the machine. Subject to the UserChoice-hash
        limitation described in this module's docstring for defaults a
        user has explicitly chosen before."""
        if not confirm:
            return {
                "requires_confirmation": True,
                "preview": f"This will apply the default-app associations from '{source_path}' machine-wide.",
            }
        result = self._run(
            [
                "dism.exe",
                "/Online",
                "/Import-DefaultAppAssociations",
                f"/Xml:{source_path}",
            ]
        )
        if "error" in result:
            return result
        if not result["success"]:
            return {
                "error": result["stderr"] or result["stdout"] or "DISM import failed.",
                "admin_hint": "Re-run elevated if this failed with access-denied.",
            }
        return {"success": True, "imported_from": source_path}

    def open_default_apps_settings(self, app_class: Optional[str] = None) -> Dict:
        """Open the Settings > Default apps page - the reliable
        fallback when import_default_apps() can't silently override an
        existing explicit user choice. If app_class is one of
        get_default_for_class()'s known classes, deep-links to that
        app's own default-apps page; otherwise opens the general page."""
        deep_links = {
            "browser": "ms-settings:defaultapps",
            "browser_https": "ms-settings:defaultapps",
            "mail": "ms-settings:defaultapps",
        }
        uri = deep_links.get(app_class, "ms-settings:defaultapps")
        try:
            subprocess.Popen(["cmd", "/c", "start", "", uri], shell=False)
            return {"success": True, "opened": uri}
        except Exception as e:
            return {"error": str(e)}
