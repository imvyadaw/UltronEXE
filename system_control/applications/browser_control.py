"""Browser Control
==================
OS-level, category-wide browser management - distinct from
apps/browsers/*.py (chrome.py, edge.py, firefox.py, brave.py,
opera.py), which each drive a *single running instance* of one named
browser via pyautogui/UI automation (open a URL, new tab, incognito,
...). This module instead operates on "browsers" as an installed
category: which ones are on this machine, which is default, and
bulk process/cache actions across all of them at once - none of which
apps/browsers/*.py covers since it assumes one already-open target
browser.

Installed-browser discovery reads
HKLM\\SOFTWARE\\Clients\\StartMenuInternet (the registry list Windows
itself uses to populate Settings > Default apps > Web browser), not
package_manager.py's generic all-programs winget/Uninstall-hive scan,
since browsers register there specifically to participate in default-
browser selection.

Setting the default browser is subject to the same UserChoice-hash
limitation as file_associations.py/default_apps.py - see
open_browser_settings() as the reliable fallback.
"""

import os
import subprocess
import winreg
from typing import Dict, List

# exe name -> friendly name, for the processes bulk actions target.
_KNOWN_BROWSER_PROCESSES = {
    "chrome.exe": "Google Chrome",
    "msedge.exe": "Microsoft Edge",
    "firefox.exe": "Mozilla Firefox",
    "brave.exe": "Brave",
    "opera.exe": "Opera",
    "iexplore.exe": "Internet Explorer",
}

# Known Chromium-family cache subpaths under %LOCALAPPDATA%, relative
# to the profile root - these are safe to delete (browser rebuilds
# them), unlike bookmarks/history/passwords which live elsewhere in
# the same profile folder.
_CHROMIUM_CACHE_PATHS = {
    "Google Chrome": r"Google\Chrome\User Data\Default\Cache",
    "Microsoft Edge": r"Microsoft\Edge\User Data\Default\Cache",
    "Brave": r"BraveSoftware\Brave-Browser\User Data\Default\Cache",
    "Opera": r"Opera Software\Opera Stable\Cache",
}


class BrowserControl:
    """Installed-browser discovery, default-browser reads, and
    bulk close/cache actions across every installed browser."""

    def _run_ps(self, script: str, timeout: float = 20.0) -> Dict:
        try:
            result = subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            return {"success": result.returncode == 0, "stdout": result.stdout.strip(), "stderr": result.stderr.strip()}
        except FileNotFoundError:
            return {"error": "powershell not found - this is only available on Windows"}
        except subprocess.TimeoutExpired:
            return {"error": "Command timed out"}
        except Exception as e:
            return {"error": str(e)}

    def list_installed_browsers(self) -> Dict:
        """List every browser registered under StartMenuInternet (the
        same list Settings > Default apps > Web browser draws from).
        No admin needed."""
        browsers: List[Dict] = []
        for hive, hive_name in ((winreg.HKEY_LOCAL_MACHINE, "HKLM"), (winreg.HKEY_CURRENT_USER, "HKCU")):
            try:
                with winreg.OpenKey(hive, r"SOFTWARE\Clients\StartMenuInternet") as root:
                    i = 0
                    while True:
                        try:
                            subkey_name = winreg.EnumKey(root, i)
                            i += 1
                        except OSError:
                            break
                        try:
                            with winreg.OpenKey(root, subkey_name) as sub:
                                display_name, _ = winreg.QueryValueEx(sub, "")
                        except OSError:
                            display_name = subkey_name
                        browsers.append({"key": subkey_name, "name": display_name, "hive": hive_name})
            except FileNotFoundError:
                continue
        # de-dupe by key, preferring the HKLM entry already listed first
        seen = set()
        unique = []
        for b in browsers:
            if b["key"] in seen:
                continue
            seen.add(b["key"])
            unique.append(b)
        return {"browsers": unique, "count": len(unique)}

    def get_default_browser(self) -> Dict:
        """Read the current default browser's ProgId. No admin needed."""
        try:
            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\Shell\Associations\UrlAssociations\http\UserChoice",
            ) as key:
                prog_id, _ = winreg.QueryValueEx(key, "ProgId")
                return {"prog_id": prog_id}
        except FileNotFoundError:
            return {"prog_id": None}
        except OSError as e:
            return {"error": str(e)}

    def open_browser_settings(self) -> Dict:
        """Open Settings > Default apps > Web browser - the reliable
        way to change the default browser given the UserChoice-hash
        protection (see this module's docstring)."""
        try:
            subprocess.Popen(["cmd", "/c", "start", "", "ms-settings:defaultapps"], shell=False)
            return {"success": True, "opened": "ms-settings:defaultapps"}
        except Exception as e:
            return {"error": str(e)}

    def close_all_browsers(self, confirm: bool = False) -> Dict:
        """Force-close every running process from
        _KNOWN_BROWSER_PROCESSES. Confirm-gated - closes windows/tabs
        without a save prompt, unlike a normal window-close."""
        if not confirm:
            return {
                "requires_confirmation": True,
                "preview": "This will force-close every running browser (Chrome, Edge, Firefox, Brave, Opera, IE).",
            }
        closed = []
        for exe in _KNOWN_BROWSER_PROCESSES:
            result = self._run_ps(
                f"Get-Process -Name '{exe[:-4]}' -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue"
            )
            if "error" not in result:
                closed.append(exe)
        return {"success": True, "attempted": closed}

    def clear_all_browsers_cache(self, confirm: bool = False) -> Dict:
        """Delete the disk-cache folder (not history/bookmarks/
        passwords/cookies) for every installed Chromium-family browser
        found on this machine. Firefox uses a different cache layout
        and isn't covered here - use apps/browsers/firefox.py or clear
        it manually. Confirm-gated, destructive."""
        if not confirm:
            return {
                "requires_confirmation": True,
                "preview": "This will delete the disk cache for every installed Chromium-family browser (Chrome, Edge, Brave, Opera).",
            }
        local_appdata = os.environ.get("LOCALAPPDATA", "")
        cleared = []
        errors = []
        for name, rel_path in _CHROMIUM_CACHE_PATHS.items():
            full_path = os.path.join(local_appdata, rel_path)
            if not os.path.isdir(full_path):
                continue
            result = self._run_ps(f"Remove-Item -Recurse -Force '{full_path}\\*' -ErrorAction SilentlyContinue; 'ok'")
            if "error" in result:
                errors.append({"browser": name, "error": result["error"]})
            else:
                cleared.append(name)
        return {"success": True, "cleared": cleared, "errors": errors}
