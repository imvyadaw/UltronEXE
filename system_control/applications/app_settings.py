"""App Settings
===============
Per-application "Advanced options" - the things Settings > Apps >
Installed apps > (an app) > Advanced options exposes for a single
app, beyond install/uninstall itself: run-as-administrator compat
flag, app execution alias enable/disable, and resetting an app's
local state.

Deliberately narrow scope to avoid overlapping existing modules:
- Default apps by file type/protocol -> system_control/files/
  file_associations.py, not here.
- Camera/mic/location per-app privacy permissions ->
  system_control/security/app_permissions.py, not here.
- An app's actual user data/cache -> app_data_backup.py / app_cache.py
  in this same package, not here.
This module is specifically the small set of per-app *compatibility
and execution* toggles that don't fit anywhere above.

Compatibility flags are written under
HKCU\\Software\\Microsoft\\Windows NT\\CurrentVersion\\AppCompatFlags\\Layers,
which is user-scope and takes effect on the exe's next launch - no
admin needed, but still confirm-gated since it changes how an
executable runs. App execution alias toggling and app reset both
require the matching Store app to exist and are also confirm-gated.
"""
import logging

import json
import subprocess
import winreg
from typing import Dict


class AppAdvancedSettings:
    """Per-app compatibility flags, execution aliases, and reset."""

    _LAYERS_PATH = r"Software\Microsoft\Windows NT\CurrentVersion\AppCompatFlags\Layers"

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

    def get_compat_flags(self, exe_path: str) -> Dict:
        """Read the current AppCompatFlags Layers string for an exe
        (e.g. 'RUNASADMIN HIGHDPIAWARE'), if any is set. No admin
        needed."""
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, self._LAYERS_PATH) as key:
                try:
                    value, _ = winreg.QueryValueEx(key, exe_path)
                    return {"exe_path": exe_path, "flags": value.split()}
                except FileNotFoundError:
                    return {"exe_path": exe_path, "flags": []}
        except FileNotFoundError:
            return {"exe_path": exe_path, "flags": []}

    def set_run_as_administrator(self, exe_path: str, enabled: bool, confirm: bool = False) -> Dict:
        """Toggle "Run this program as an administrator" for one exe -
        adds/removes RUNASADMIN from its compat-flags layer string
        while preserving any other flags already set. Confirm-gated."""
        if not confirm:
            action = "enable" if enabled else "disable"
            return {
                "requires_confirmation": True,
                "preview": f"This will {action} 'Run as administrator' for {exe_path}.",
            }
        current = self.get_compat_flags(exe_path)
        flags = set(current.get("flags", []))
        if enabled:
            flags.add("RUNASADMIN")
        else:
            flags.discard("RUNASADMIN")

        try:
            with winreg.CreateKey(winreg.HKEY_CURRENT_USER, self._LAYERS_PATH) as key:
                if flags:
                    winreg.SetValueEx(key, exe_path, 0, winreg.REG_SZ, " ".join(sorted(flags)))
                else:
                    try:
                        winreg.DeleteValue(key, exe_path)
                    except FileNotFoundError:
                        logging.getLogger(__name__).exception("Suppressed FileNotFoundError")
            return {"success": True, "exe_path": exe_path, "run_as_admin": enabled, "flags": sorted(flags)}
        except OSError as e:
            return {"error": str(e)}

    def list_app_execution_aliases(self) -> Dict:
        """List Store-app execution aliases (the `App execution aliases`
        Settings page - lets a Store app claim a command name like
        `python.exe` in PATH) and whether each is currently enabled.
        No admin needed."""
        data = self._run_json(
            'Get-ChildItem "$env:LOCALAPPDATA\\Microsoft\\WindowsApps" -ErrorAction SilentlyContinue | '
            "Where-Object { $_.Extension -eq '.exe' } | "
            "ForEach-Object { [PSCustomObject]@{ Name = $_.Name; Path = $_.FullName; "
            "IsReparsePoint = [bool]($_.Attributes -band [IO.FileAttributes]::ReparsePoint) } }"
        )
        if isinstance(data, dict) and "error" in data:
            return data
        return {"aliases": data, "count": len(data)}

    def set_app_execution_alias(self, alias_name: str, enabled: bool, confirm: bool = False) -> Dict:
        """Enable/disable one execution alias by renaming its reparse
        point in %LOCALAPPDATA%\\Microsoft\\WindowsApps (Windows has no
        documented cmdlet for this; Settings itself just adds/removes
        the alias's placeholder file). Disabling renames it to
        `<name>.disabled` so it can be restored; enabling reverses
        that. Confirm-gated - changes which binary a command name on
        PATH resolves to."""
        if not confirm:
            action = "enable" if enabled else "disable"
            return {
                "requires_confirmation": True,
                "preview": f"This will {action} the '{alias_name}' app execution alias.",
            }
        base = r"$env:LOCALAPPDATA\Microsoft\WindowsApps"
        if enabled:
            src, dst = f"{alias_name}.disabled", alias_name
        else:
            src, dst = alias_name, f"{alias_name}.disabled"
        result = self._run_ps(
            f"$src = Join-Path {base} '{src}'; $dst = Join-Path {base} '{dst}'; "
            f"if (Test-Path $src) {{ Rename-Item -Path $src -NewName (Split-Path $dst -Leaf) -Force; 'ok' }} "
            f"else {{ 'notfound' }}"
        )
        if "error" in result:
            return result
        if not result["success"]:
            return {"error": result["stderr"] or "Failed to toggle execution alias."}
        if "notfound" in result["stdout"]:
            return {"error": f"No alias file found for '{alias_name}' in its expected state."}
        return {"success": True, "alias_name": alias_name, "enabled": enabled}

    def reset_app(self, package_family_name: str, confirm: bool = False) -> Dict:
        """Reset a UWP/Store app's local state - clears its data and
        preferences as if freshly installed (equivalent to Settings'
        "Reset" button), without uninstalling it. Confirm-gated and
        not reversible; the app's saved state is gone."""
        if not confirm:
            return {
                "requires_confirmation": True,
                "preview": f"This will reset '{package_family_name}' to its default state, erasing its local data.",
            }
        result = self._run_ps(
            f'Invoke-Expression "& \\"$env:windir\\System32\\WindowsApps\\" " 2>$null; '
            f"$pkg = Get-AppxPackage | Where-Object {{ $_.PackageFamilyName -eq '{package_family_name}' }}; "
            f"if (-not $pkg) {{ 'notfound' }} else {{ "
            f'Remove-Item -Recurse -Force "$env:LOCALAPPDATA\\Packages\\{package_family_name}\\LocalState" '
            f"-ErrorAction SilentlyContinue; 'ok' }}"
        )
        if "error" in result:
            return result
        if not result["success"]:
            return {"error": result["stderr"] or "Reset failed."}
        if "notfound" in result["stdout"]:
            return {"error": f"No installed package with family name '{package_family_name}'."}
        return {"success": True, "package_family_name": package_family_name, "reset": True}
