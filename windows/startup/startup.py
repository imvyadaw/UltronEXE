"""Startup program manager
========================
List/add/remove programs that launch automatically when Windows starts,
via the HKCU Run registry key (per-user, no admin needed) and the
per-user Startup folder shortcut approach.
"""

import os
from pathlib import Path
from typing import Dict

try:
    import winreg

    HAS_WINREG = True
except ImportError:
    HAS_WINREG = False

RUN_KEY_PATH = r"Software\Microsoft\Windows\CurrentVersion\Run"


class StartupTools:
    """Manage per-user Windows startup programs (HKCU Run key)."""

    def list_startup_programs(self) -> Dict:
        """List programs registered to launch at login (current user only)."""
        if not HAS_WINREG:
            return {"error": "Startup registry access is only available on Windows"}
        try:
            programs = []
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY_PATH) as key:
                i = 0
                while True:
                    try:
                        name, command, _ = winreg.EnumValue(key, i)
                        programs.append({"name": name, "command": command})
                        i += 1
                    except OSError:
                        break

            startup_folder = Path(os.environ.get("APPDATA", "")) / "Microsoft/Windows/Start Menu/Programs/Startup"
            folder_items = []
            if startup_folder.exists():
                folder_items = [f.name for f in startup_folder.iterdir()]

            return {
                "registry_entries": programs,
                "startup_folder": str(startup_folder),
                "startup_folder_items": folder_items,
            }
        except Exception as e:
            return {"error": str(e)}

    def add_startup_program(self, name: str, command: str) -> Dict:
        """Register a program to launch at login for the current user."""
        if not HAS_WINREG:
            return {"error": "Startup registry access is only available on Windows"}
        try:
            with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, RUN_KEY_PATH) as key:
                winreg.SetValueEx(key, name, 0, winreg.REG_SZ, command)
            return {"success": True, "name": name, "command": command}
        except Exception as e:
            return {"error": str(e)}

    def remove_startup_program(self, name: str, confirm: bool = False) -> Dict:
        """Remove a program from the current user's startup list. Safety-gated: needs confirm=true."""
        if not HAS_WINREG:
            return {"error": "Startup registry access is only available on Windows"}
        if not confirm:
            return {"error": f"This will remove '{name}' from startup. Call again with confirm=true to proceed."}
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY_PATH, 0, winreg.KEY_SET_VALUE) as key:
                winreg.DeleteValue(key, name)
            return {"success": True, "removed": name}
        except FileNotFoundError:
            return {"error": f"No startup entry named '{name}'"}
        except Exception as e:
            return {"error": str(e)}
