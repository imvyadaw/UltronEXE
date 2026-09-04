"""
Windows Registry automation
==============================
Read-only-by-default helpers over `winreg` for inspecting the registry,
plus explicit write/delete methods for when the AI has been asked to
change a specific value - both return clear errors rather than silently
failing, since registry edits can affect the whole system.
"""

from typing import Dict

from apps.base_app import BaseApp

try:
    import winreg

    HAS_WINREG = True
except ImportError:
    HAS_WINREG = False

_ROOTS = {
    "HKEY_CURRENT_USER": "HKCU",
    "HKCU": "HKCU",
    "HKEY_LOCAL_MACHINE": "HKLM",
    "HKLM": "HKLM",
    "HKEY_CLASSES_ROOT": "HKCR",
    "HKCR": "HKCR",
    "HKEY_USERS": "HKU",
    "HKU": "HKU",
}


class RegistryApp(BaseApp):
    """Open regedit and read/write/list registry keys and values."""

    APP_NAME = "regedit"
    PROCESS_NAMES = ["regedit.exe", "regedit"]
    EXE_HINTS = ["regedit", "regedit.exe"]

    def _root_handle(self, root: str):
        mapping = {
            "HKCU": winreg.HKEY_CURRENT_USER,
            "HKLM": winreg.HKEY_LOCAL_MACHINE,
            "HKCR": winreg.HKEY_CLASSES_ROOT,
            "HKU": winreg.HKEY_USERS,
        }
        return mapping[_ROOTS[root.upper()]]

    def read_value(self, root: str, key_path: str, value_name: str) -> Dict:
        if not HAS_WINREG:
            return {"error": "winreg is only available on Windows"}
        try:
            handle = self._root_handle(root)
            with winreg.OpenKey(handle, key_path) as key:
                value, value_type = winreg.QueryValueEx(key, value_name)
                return {"success": True, "value": value, "type": value_type}
        except Exception as e:
            return {"error": str(e)}

    def list_values(self, root: str, key_path: str) -> Dict:
        if not HAS_WINREG:
            return {"error": "winreg is only available on Windows"}
        try:
            handle = self._root_handle(root)
            values = []
            with winreg.OpenKey(handle, key_path) as key:
                i = 0
                while True:
                    try:
                        name, value, vtype = winreg.EnumValue(key, i)
                        values.append({"name": name, "value": value, "type": vtype})
                        i += 1
                    except OSError:
                        break
            return {"success": True, "values": values}
        except Exception as e:
            return {"error": str(e)}

    def set_value(self, root: str, key_path: str, value_name: str, value, value_type: str = "REG_SZ") -> Dict:
        if not HAS_WINREG:
            return {"error": "winreg is only available on Windows"}
        try:
            handle = self._root_handle(root)
            reg_type = getattr(winreg, value_type, winreg.REG_SZ)
            with winreg.CreateKeyEx(handle, key_path, 0, winreg.KEY_SET_VALUE) as key:
                winreg.SetValueEx(key, value_name, 0, reg_type, value)
            return {"success": True, "key_path": key_path, "value_name": value_name}
        except Exception as e:
            return {"error": str(e)}
