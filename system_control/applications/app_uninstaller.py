"""App Uninstaller
==================
Removes installed applications - Win32 programs via their registered
uninstaller (preferring `winget uninstall` when the package is known
to winget, falling back to the registry's raw UninstallString when
it isn't) and UWP/Store apps via `Remove-AppxPackage`.

Distinct from package_manager.py (which only discovers/installs, never
removes) and from app_data_backup.py/app_cache.py (which clean up an
app's leftover data - this module's job ends once the app itself is
gone; leftover_scan/force_remove_leftovers here only look at what the
uninstaller *itself* left behind, not a general data wipe).

Every state-changing method is confirm-gated: uninstalling a program
is not reliably reversible (no universal "undo"), and force-removing
leftovers deletes files/registry entries outside of any uninstaller's
control, which is a step further than the vendor's own removal tool
would go.
"""
import logging

import json
import os
import shutil
import subprocess
import winreg
from typing import Dict, List, Optional


class AppUninstaller:
    """Uninstall Win32 and UWP applications."""

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

    def _find_win32_entry(self, name: str) -> Optional[Dict]:
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

                                def _get(n):
                                    try:
                                        return winreg.QueryValueEx(sub, n)[0]
                                    except FileNotFoundError:
                                        return None

                                display_name = _get("DisplayName")
                                if display_name and name.lower() in display_name.lower():
                                    return {
                                        "name": display_name,
                                        "uninstall_string": _get("UninstallString"),
                                        "quiet_uninstall_string": _get("QuietUninstallString"),
                                        "install_location": _get("InstallLocation"),
                                        "registry_root": "HKLM" if root == winreg.HKEY_LOCAL_MACHINE else "HKCU",
                                        "registry_path": f"{path}\\{subkey_name}",
                                    }
                        except OSError:
                            continue
            except FileNotFoundError:
                continue
        return None

    def get_uninstall_command(self, app_name: str) -> Dict:
        """Look up how a Win32 app would be uninstalled, without
        running anything. No admin needed."""
        entry = self._find_win32_entry(app_name)
        if not entry:
            return {"error": f"No installed app matching '{app_name}' found in the Uninstall registry."}
        return entry

    def uninstall_app(self, app_name: str, confirm: bool = False) -> Dict:
        """Uninstall a Win32 app. Tries `winget uninstall` first (cleaner,
        handles silent-flag differences across installers itself); if
        winget doesn't recognize it, falls back to running the
        registry's own QuietUninstallString/UninstallString directly.
        Confirm-gated."""
        if not confirm:
            entry = self._find_win32_entry(app_name)
            preview = (
                f"This will uninstall '{entry['name']}'."
                if entry
                else f"This will attempt to uninstall an app matching '{app_name}' via winget."
            )
            return {"requires_confirmation": True, "preview": preview}

        winget = (
            subprocess.run(
                [
                    "winget",
                    "uninstall",
                    "--name",
                    app_name,
                    "--silent",
                    "--accept-source-agreements",
                    "--disable-interactivity",
                ],
                capture_output=True,
                text=True,
                timeout=300,
            )
            if shutil.which("winget")
            else None
        )

        if winget and winget.returncode == 0:
            return {"success": True, "app_name": app_name, "method": "winget", "uninstalled": True}

        entry = self._find_win32_entry(app_name)
        if not entry:
            reason = winget.stderr.strip() if winget else "winget not available"
            return {"error": f"Could not uninstall '{app_name}': {reason}, and no registry Uninstall entry found."}

        cmd = entry.get("quiet_uninstall_string") or entry.get("uninstall_string")
        if not cmd:
            return {"error": f"Found '{entry['name']}' but it has no uninstall command registered."}

        try:
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=300)
            return {
                "success": result.returncode == 0,
                "app_name": entry["name"],
                "method": "registry_uninstall_string",
                "uninstalled": result.returncode == 0,
                "returncode": result.returncode,
                "stderr": result.stderr.strip(),
            }
        except subprocess.TimeoutExpired:
            return {"error": "Uninstaller timed out - it may be waiting on a UI prompt."}
        except Exception as e:
            return {"error": str(e)}

    def list_appx_packages(self, name_filter: str = None) -> Dict:
        """List installed UWP/Store packages, optionally filtered by
        (partial) name. No admin needed."""
        script = "Get-AppxPackage"
        if name_filter:
            script += f" -Name '*{name_filter}*'"
        data = self._run_json(f"{script} | Select-Object Name, PackageFullName, Version, IsFramework")
        if isinstance(data, dict) and "error" in data:
            return data
        return {"packages": data, "count": len(data)}

    def uninstall_appx_package(self, package_full_name: str, confirm: bool = False) -> Dict:
        """Remove a UWP/Store app by its PackageFullName (from
        list_appx_packages). Confirm-gated."""
        if not confirm:
            return {
                "requires_confirmation": True,
                "preview": f"This will remove the UWP app package '{package_full_name}'.",
            }
        result = self._run_ps(f"Remove-AppxPackage -Package '{package_full_name}'")
        if "error" in result:
            return result
        if not result["success"]:
            return {"error": result["stderr"] or "Remove-AppxPackage failed."}
        return {"success": True, "package_full_name": package_full_name, "removed": True}

    def scan_leftovers(self, app_name: str) -> Dict:
        """After uninstalling, look for common leftover locations
        (Program Files directories and AppData folders matching the
        app name) that the uninstaller may not have cleaned up.
        Read-only - just reports what it finds."""
        candidates = []
        search_roots = [
            os.environ.get("ProgramFiles", r"C:\Program Files"),
            os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"),
            os.environ.get("LOCALAPPDATA", ""),
            os.environ.get("APPDATA", ""),
        ]
        for root in search_roots:
            if not root or not os.path.isdir(root):
                continue
            try:
                for entry in os.listdir(root):
                    if app_name.lower() in entry.lower():
                        full = os.path.join(root, entry)
                        size = 0
                        for dirpath, _, filenames in os.walk(full):
                            for f in filenames:
                                try:
                                    size += os.path.getsize(os.path.join(dirpath, f))
                                except OSError:
                                    logging.getLogger(__name__).exception("Suppressed OSError")
                        candidates.append({"path": full, "approx_size_bytes": size})
            except OSError:
                continue
        return {"leftovers": candidates, "count": len(candidates)}

    def force_remove_leftovers(self, paths: List[str], confirm: bool = False) -> Dict:
        """Permanently delete specific leftover folders/files reported
        by scan_leftovers. Confirm-gated and irreversible - unlike
        Windows' Recycle Bin, this is a direct filesystem delete."""
        if not confirm:
            return {
                "requires_confirmation": True,
                "preview": f"This will permanently delete {len(paths)} path(s): {', '.join(paths[:5])}"
                f"{' ...' if len(paths) > 5 else ''}",
            }
        removed, failed = [], []
        for path in paths:
            try:
                if os.path.isdir(path):
                    shutil.rmtree(path)
                elif os.path.isfile(path):
                    os.remove(path)
                else:
                    failed.append({"path": path, "error": "not found"})
                    continue
                removed.append(path)
            except Exception as e:
                failed.append({"path": path, "error": str(e)})
        return {"removed": removed, "failed": failed, "removed_count": len(removed)}
