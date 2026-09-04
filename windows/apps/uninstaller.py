"""App uninstaller
===============
List installed Windows programs (from the same registry "Uninstall"
keys Control Panel > Programs and Features reads) and uninstall one
by running the uninstaller it registered for itself. New in Phase 8 -
Phase 7's AppManager (windows/apps/manager.py, also exposed here as
AppLauncher) only covers launching/closing/finding apps, not removing
them.

Design notes:
- Reads three registry locations to match what Programs and Features
  shows: 64-bit apps, 32-bit apps on a 64-bit OS (WOW6432Node), and
  per-user installs (HKCU). SystemComponent=1 entries (OS/runtime
  pieces not meant to be individually uninstalled, e.g. some VC++
  redistributable sub-parts) are skipped by default.
- Uninstalling always runs the vendor's own registered uninstaller -
  nothing here deletes files/registry entries directly. That keeps
  behavior identical to what a person would get double-clicking
  "Uninstall" in Control Panel.
- Silent uninstall is only attempted when the entry itself provides a
  QuietUninstallString, or for MSI-based installs (well-defined
  `msiexec /X{GUID} /quiet` form). For everything else, guessing
  silent-switches for an arbitrary vendor .exe is unreliable and
  risks passing a flag that installer doesn't actually support, so
  the vendor's normal (interactive) uninstaller runs instead.
- Safety-gated like every other destructive method in this codebase:
  needs confirm=true.
"""

import re
import subprocess
from typing import Dict, List, Optional

try:
    import winreg

    HAS_WINREG = True
except ImportError:
    HAS_WINREG = False

_UNINSTALL_KEY_PATHS = [
    (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall") if HAS_WINREG else (None, None),
    (
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall")
        if HAS_WINREG
        else (None, None)
    ),
    (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall") if HAS_WINREG else (None, None),
]


class AppUninstaller:
    """List installed programs and uninstall via their registered uninstaller."""

    def __init__(self):
        self._cache: Optional[List[Dict]] = None

    def _read_entry(self, hive, subkey_path: str, entry_name: str) -> Optional[Dict]:
        try:
            with winreg.OpenKey(hive, f"{subkey_path}\\{entry_name}") as key:

                def _get(name, default=None):
                    try:
                        return winreg.QueryValueEx(key, name)[0]
                    except FileNotFoundError:
                        return default

                display_name = _get("DisplayName")
                if not display_name:
                    return None  # entries without a DisplayName aren't real listed programs
                return {
                    "key_name": entry_name,
                    "name": display_name,
                    "version": _get("DisplayVersion", ""),
                    "publisher": _get("Publisher", ""),
                    "install_date": _get("InstallDate", ""),
                    "estimated_size_kb": _get("EstimatedSize"),
                    "uninstall_string": _get("UninstallString"),
                    "quiet_uninstall_string": _get("QuietUninstallString"),
                    "system_component": bool(_get("SystemComponent", 0)),
                }
        except OSError:
            return None

    def get_installed_programs(self, include_system: bool = False, refresh: bool = False) -> List[Dict]:
        """Enumerate installed programs from the registry Uninstall keys. Cached after first call."""
        if self._cache is not None and not refresh:
            return self._cache if include_system else [p for p in self._cache if not p["system_component"]]

        programs = []
        seen_names = set()
        for hive, path in _UNINSTALL_KEY_PATHS:
            if hive is None:
                continue
            try:
                with winreg.OpenKey(hive, path) as root:
                    i = 0
                    while True:
                        try:
                            subkey_name = winreg.EnumKey(root, i)
                        except OSError:
                            break
                        i += 1
                        entry = self._read_entry(hive, path, subkey_name)
                        if entry and entry["name"] not in seen_names:
                            seen_names.add(entry["name"])
                            programs.append(entry)
            except OSError:
                continue

        programs.sort(key=lambda p: p["name"].lower())
        self._cache = programs
        return programs if include_system else [p for p in programs if not p["system_component"]]

    def list_installed_programs(self, include_system: bool = False) -> Dict:
        """List installed programs (name/version/publisher) - the AppUninstaller equivalent
        of Control Panel > Programs and Features."""
        if not HAS_WINREG:
            return {"error": "winreg is only available on Windows"}
        try:
            programs = self.get_installed_programs(include_system=include_system)
            summary = [{"name": p["name"], "version": p["version"], "publisher": p["publisher"]} for p in programs]
            return {"count": len(summary), "programs": summary}
        except Exception as e:
            return {"error": str(e)}

    def find_program(self, query: str) -> Optional[Dict]:
        """Find an installed program by partial, case-insensitive name match."""
        programs = self.get_installed_programs(include_system=True)
        query_lower = query.lower()
        for p in programs:
            if p["name"].lower() == query_lower:
                return p
        for p in programs:
            if query_lower in p["name"].lower():
                return p
        return None

    def _build_uninstall_command(self, entry: Dict, silent: bool) -> str:
        quiet = entry.get("quiet_uninstall_string")
        if silent and quiet:
            return quiet

        uninstall_string = entry.get("uninstall_string") or ""

        # MSI-based installs have a well-defined silent form: swap /I for /X
        # (or add /X<guid> if the string only names msiexec) plus /quiet /norestart.
        if "msiexec" in uninstall_string.lower():
            guid_match = re.search(r"\{[0-9A-Fa-f\-]{36}\}", uninstall_string) or re.search(
                r"\{[0-9A-Fa-f\-]{36}\}", entry.get("key_name", "")
            )
            if guid_match:
                guid = guid_match.group(0)
                if silent:
                    return f"msiexec /X{guid} /quiet /norestart"
                return f"msiexec /X{guid}"
            return uninstall_string

        # Anything else: run the vendor's own uninstaller as registered. Not
        # guessing extra silent switches here - an unsupported flag passed to
        # an arbitrary vendor .exe is more likely to break the uninstall than
        # help it, so this runs interactively (the same experience as
        # Control Panel > Uninstall for a non-MSI app).
        return uninstall_string

    def uninstall_program(self, name: str, confirm: bool = False, silent: bool = True) -> Dict:
        """Uninstall an installed program by (partial) name, using its own registered
        uninstaller. Safety-gated: needs confirm=true. silent=True only takes effect
        when the program provides a genuine silent-uninstall string (MSI installs, or
        an explicit QuietUninstallString) - otherwise its normal uninstaller runs."""
        if not HAS_WINREG:
            return {"error": "winreg is only available on Windows"}
        entry = self.find_program(name)
        if not entry:
            return {"error": f"No installed program matching '{name}'"}
        if not entry.get("uninstall_string") and not entry.get("quiet_uninstall_string"):
            return {"error": f"'{entry['name']}' has no registered uninstaller"}
        if not confirm:
            return {
                "error": f"This will uninstall '{entry['name']}'. Call again with confirm=true to proceed.",
                "matched_program": entry["name"],
                "version": entry.get("version"),
                "publisher": entry.get("publisher"),
            }
        try:
            command = self._build_uninstall_command(entry, silent=silent)
            subprocess.Popen(command, shell=True)
            return {
                "success": True,
                "uninstalling": entry["name"],
                "mode": (
                    "silent"
                    if (silent and (entry.get("quiet_uninstall_string") or "msiexec" in command.lower()))
                    else "interactive"
                ),
                "note": "Uninstaller launched - it may show its own confirmation UI depending on the app.",
            }
        except Exception as e:
            return {"error": str(e)}
