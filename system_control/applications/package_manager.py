"""Package Manager
==================
Discovery layer for what's installed and what's available, wrapping
Windows' package front-ends: `winget` (the modern CLI package manager
that fronts both the Microsoft Store and classic installers) for
search/install, and the classic Win32 "Uninstall" registry hive
(HKLM/HKCU ...\\Uninstall) plus `Get-AppxPackage` (UWP/Store apps) for
enumerating what's already on the machine - winget's own `list`
undercounts silently-installed or manually-copied Win32 apps that
never registered with it, so registry enumeration is kept as the
ground truth for "what's installed" and winget is used for "what's
searchable/installable".

Distinct from app_uninstaller.py (removal), app_updater.py (version
checking/upgrading already-known packages), app_settings.py (per-app
Windows Settings-pane toggles), app_data_backup.py (an app's user
data), and app_cache.py (an app's cache/temp footprint) - this module
only answers "what exists" and "get me a new one", nothing further.

install_package is confirm-gated since it downloads and executes an
installer with the privileges winget itself runs at; everything else
here is read-only.
"""

import json
import re
import subprocess
import winreg
from typing import Dict, List


class PackageManager:
    """List installed packages (Win32 + UWP) and search/install new
    ones via winget."""

    _UNINSTALL_ROOTS = [
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"),
        (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
    ]

    def _run_ps(self, script: str, timeout: float = 30.0) -> Dict:
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

    def _run_json(self, script: str, timeout: float = 30.0):
        result = self._run_ps(f"{script} | ConvertTo-Json -Depth 4 -Compress", timeout)
        if "error" in result:
            return result
        if not result["success"]:
            return {"error": result["stderr"] or "Command failed."}
        if not result["stdout"]:
            return []
        try:
            data = json.loads(result["stdout"])
        except json.JSONDecodeError:
            return {"error": "Could not parse PowerShell output."}
        return data if isinstance(data, list) else [data]

    def _run_winget(self, args: List[str], timeout: float = 60.0) -> Dict:
        try:
            result = subprocess.run(
                ["winget"] + args + ["--accept-source-agreements", "--disable-interactivity"],
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            return {
                "success": result.returncode == 0,
                "stdout": result.stdout.strip(),
                "stderr": result.stderr.strip(),
                "returncode": result.returncode,
            }
        except FileNotFoundError:
            return {"error": "winget not found - requires App Installer from the Microsoft Store"}
        except subprocess.TimeoutExpired:
            return {"error": "Command timed out"}
        except Exception as e:
            return {"error": str(e)}

    @staticmethod
    def _parse_winget_table(stdout: str) -> List[Dict]:
        """winget's default output is a fixed-width text table with no
        machine-readable mode for list/search, so this splits on the
        header's column boundaries (found via the '---' separator row)
        rather than whitespace, since names/publishers can contain
        spaces."""
        lines = stdout.splitlines()
        sep_idx = next((i for i, l in enumerate(lines) if re.match(r"^-+\s", l) or set(l.strip()) == {"-"}), None)
        if sep_idx is None or sep_idx == 0:
            return []
        header = lines[sep_idx - 1]
        sep = lines[sep_idx]
        # Column starts = positions where the separator has a run of
        # dashes beginning right after a space (or position 0).
        bounds = [m.start() for m in re.finditer(r"(?:^|(?<= ))-+", sep)]
        bounds.append(len(header) + 1)
        cols = [header[bounds[i] : bounds[i + 1]].strip() for i in range(len(bounds) - 1)]
        rows = []
        for line in lines[sep_idx + 1 :]:
            if not line.strip():
                continue
            values = [line[bounds[i] : bounds[i + 1]].strip() for i in range(len(bounds) - 1)]
            rows.append(dict(zip(cols, values)))
        return rows

    def list_installed_packages(self, include_appx: bool = True) -> Dict:
        """Enumerate every installed Win32 program from the registry
        Uninstall hive (the same list Control Panel > Programs and
        Features reads from), plus UWP/Store packages if requested.
        No admin needed."""
        win32_apps = []
        for root, path in self._UNINSTALL_ROOTS:
            try:
                with winreg.OpenKey(root, path) as key:
                    i = 0
                    while True:
                        try:
                            subkey_name = winreg.EnumKey(key, i)
                        except OSError:
                            break
                        i += 1
                        try:
                            with winreg.OpenKey(key, subkey_name) as sub:

                                def _get(name):
                                    try:
                                        return winreg.QueryValueEx(sub, name)[0]
                                    except FileNotFoundError:
                                        return None

                                display_name = _get("DisplayName")
                                if not display_name:
                                    continue
                                win32_apps.append(
                                    {
                                        "name": display_name,
                                        "version": _get("DisplayVersion"),
                                        "publisher": _get("Publisher"),
                                        "install_location": _get("InstallLocation"),
                                        "uninstall_string": _get("UninstallString"),
                                        "registry_key": subkey_name,
                                    }
                                )
                        except OSError:
                            continue
            except FileNotFoundError:
                continue

        result = {"win32_apps": win32_apps, "win32_count": len(win32_apps)}

        if include_appx:
            appx = self._run_json(
                "Get-AppxPackage | Select-Object Name, PackageFullName, Version, Publisher, InstallLocation"
            )
            if isinstance(appx, dict) and "error" in appx:
                result["appx_error"] = appx["error"]
            else:
                result["appx_apps"] = appx
                result["appx_count"] = len(appx)

        return result

    def get_package_info(self, name: str) -> Dict:
        """Look up one installed Win32 app by (partial, case-insensitive)
        display name."""
        data = self.list_installed_packages(include_appx=False)
        matches = [a for a in data["win32_apps"] if name.lower() in (a["name"] or "").lower()]
        if not matches:
            return {"error": f"No installed app matching '{name}'."}
        return {"matches": matches, "count": len(matches)}

    def search_available(self, query: str) -> Dict:
        """Search the winget catalog (Microsoft Store + winget's
        curated community repo) for installable packages by name."""
        result = self._run_winget(["search", query, "--source", "winget"])
        if "error" in result:
            return result
        if not result["success"] and "No package found" in (result["stdout"] + result["stderr"]):
            return {"results": [], "count": 0}
        if not result["success"]:
            return {"error": result["stderr"] or "winget search failed."}
        rows = self._parse_winget_table(result["stdout"])
        return {"results": rows, "count": len(rows)}

    def list_winget_sources(self) -> Dict:
        """List configured winget package sources (winget, msstore, ...)."""
        result = self._run_winget(["source", "list"])
        if "error" in result:
            return result
        if not result["success"]:
            return {"error": result["stderr"] or "winget source list failed."}
        return {"sources": self._parse_winget_table(result["stdout"])}

    def install_package(self, package_id: str, confirm: bool = False) -> Dict:
        """Install a package by its winget package identifier (from
        search_available's 'Id' column). Confirm-gated - runs an
        arbitrary vendor installer, which can itself make further
        system changes winget doesn't report on."""
        if not confirm:
            return {
                "requires_confirmation": True,
                "preview": f"This will download and install '{package_id}' via winget.",
            }
        result = self._run_winget(["install", "--id", package_id, "--exact", "--silent"], timeout=600.0)
        if "error" in result:
            return result
        if not result["success"]:
            return {
                "error": result["stderr"] or result["stdout"] or "winget install failed.",
                "returncode": result["returncode"],
            }
        return {"success": True, "package_id": package_id, "installed": True, "output": result["stdout"][-2000:]}
