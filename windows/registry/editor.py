"""Windows Registry editor
========================
Read/write/list/delete Windows Registry keys and values via the
stdlib `winreg` module (Windows-only - importing this on another OS
just disables these methods with a clear error, same pattern as
pycaw/pywinauto elsewhere).

Renamed from registry/registry.py (RegistryTools) as part of Phase 8's
windows/ restructure. Only windows/__init__.py imported the old
module, so this is a clean rename. Adds create_key/delete_key so the
module actually covers full key CRUD, not just values, matching the
"editor" name.

Safety model unchanged from Phase 7: writes/creates/deletes are only
allowed under HKCU (no admin required, and it's the user's own hive -
HKLM/HKCR/etc. would need admin and can affect the whole machine, so
those roots stay read-only here).
"""

from typing import Dict

try:
    import winreg

    HAS_WINREG = True
except ImportError:
    HAS_WINREG = False

ROOT_KEYS = {
    "HKCU": "HKEY_CURRENT_USER",
    "HKLM": "HKEY_LOCAL_MACHINE",
    "HKCR": "HKEY_CLASSES_ROOT",
    "HKU": "HKEY_USERS",
    "HKCC": "HKEY_CURRENT_CONFIG",
}

if HAS_WINREG:
    _ROOT_MAP = {
        "HKCU": winreg.HKEY_CURRENT_USER,
        "HKLM": winreg.HKEY_LOCAL_MACHINE,
        "HKCR": winreg.HKEY_CLASSES_ROOT,
        "HKU": winreg.HKEY_USERS,
        "HKCC": winreg.HKEY_CURRENT_CONFIG,
    }


class RegistryEditor:
    """Read/write/list/delete Windows Registry keys. Root must be one of HKCU/HKLM/HKCR/HKU/HKCC."""

    def _root(self, root: str):
        root = root.upper()
        if root not in _ROOT_MAP:
            raise ValueError(f"Unknown registry root '{root}' - use one of {list(ROOT_KEYS)}")
        return _ROOT_MAP[root]

    def read_value(self, root: str, key_path: str, value_name: str) -> Dict:
        """Read a single registry value, e.g. root='HKCU', key_path='Software\\Microsoft\\Windows\\CurrentVersion\\Run'."""
        if not HAS_WINREG:
            return {"error": "winreg is only available on Windows"}
        try:
            with winreg.OpenKey(self._root(root), key_path) as key:
                value, value_type = winreg.QueryValueEx(key, value_name)
                return {
                    "root": root,
                    "key_path": key_path,
                    "value_name": value_name,
                    "value": value,
                    "type": value_type,
                }
        except FileNotFoundError:
            return {"error": f"Key/value not found: {root}\\{key_path}\\{value_name}"}
        except Exception as e:
            return {"error": str(e)}

    def list_values(self, root: str, key_path: str) -> Dict:
        """List all values under a registry key."""
        if not HAS_WINREG:
            return {"error": "winreg is only available on Windows"}
        try:
            values = []
            with winreg.OpenKey(self._root(root), key_path) as key:
                i = 0
                while True:
                    try:
                        name, value, vtype = winreg.EnumValue(key, i)
                        values.append({"name": name, "value": value, "type": vtype})
                        i += 1
                    except OSError:
                        break
            return {"root": root, "key_path": key_path, "values": values, "count": len(values)}
        except FileNotFoundError:
            return {"error": f"Key not found: {root}\\{key_path}"}
        except Exception as e:
            return {"error": str(e)}

    def list_subkeys(self, root: str, key_path: str) -> Dict:
        """List subkey names under a registry key."""
        if not HAS_WINREG:
            return {"error": "winreg is only available on Windows"}
        try:
            subkeys = []
            with winreg.OpenKey(self._root(root), key_path) as key:
                i = 0
                while True:
                    try:
                        subkeys.append(winreg.EnumKey(key, i))
                        i += 1
                    except OSError:
                        break
            return {"root": root, "key_path": key_path, "subkeys": subkeys, "count": len(subkeys)}
        except FileNotFoundError:
            return {"error": f"Key not found: {root}\\{key_path}"}
        except Exception as e:
            return {"error": str(e)}

    def write_value(self, root: str, key_path: str, value_name: str, value, value_type: str = "REG_SZ") -> Dict:
        """Write a registry value. Only HKCU is allowed - other roots need admin and are
        blocked here to avoid silently breaking the system."""
        if not HAS_WINREG:
            return {"error": "winreg is only available on Windows"}
        if root.upper() != "HKCU":
            return {"error": "Only HKCU writes are allowed (HKLM/etc. need admin and can affect the whole system)"}
        try:
            type_map = {
                "REG_SZ": winreg.REG_SZ,
                "REG_DWORD": winreg.REG_DWORD,
                "REG_EXPAND_SZ": winreg.REG_EXPAND_SZ,
            }
            reg_type = type_map.get(value_type, winreg.REG_SZ)
            with winreg.CreateKeyEx(self._root(root), key_path) as key:
                winreg.SetValueEx(key, value_name, 0, reg_type, value)
            return {"success": True, "root": root, "key_path": key_path, "value_name": value_name, "value": value}
        except Exception as e:
            return {"error": str(e)}

    def create_key(self, root: str, key_path: str) -> Dict:
        """Create a new (possibly empty) registry key. Only HKCU is allowed."""
        if not HAS_WINREG:
            return {"error": "winreg is only available on Windows"}
        if root.upper() != "HKCU":
            return {"error": "Only HKCU key creation is allowed (HKLM/etc. need admin and can affect the whole system)"}
        try:
            with winreg.CreateKeyEx(self._root(root), key_path):
                pass
            return {"success": True, "root": root, "key_path": key_path, "created": True}
        except Exception as e:
            return {"error": str(e)}

    def delete_value(self, root: str, key_path: str, value_name: str, confirm: bool = False) -> Dict:
        """Delete a single registry value. Only HKCU is allowed. Safety-gated: needs confirm=true."""
        if not HAS_WINREG:
            return {"error": "winreg is only available on Windows"}
        if root.upper() != "HKCU":
            return {"error": "Only HKCU deletes are allowed"}
        if not confirm:
            return {
                "error": f"This will delete registry value '{value_name}'. Call again with confirm=true to proceed."
            }
        try:
            with winreg.OpenKey(self._root(root), key_path, 0, winreg.KEY_SET_VALUE) as key:
                winreg.DeleteValue(key, value_name)
            return {"success": True, "deleted": value_name}
        except FileNotFoundError:
            return {"error": f"Value not found: {value_name}"}
        except Exception as e:
            return {"error": str(e)}

    def delete_key(self, root: str, key_path: str, confirm: bool = False) -> Dict:
        """Delete a registry key. The key must have no subkeys (winreg.DeleteKey's
        own limitation - delete children first). Only HKCU is allowed.
        Safety-gated: needs confirm=true."""
        if not HAS_WINREG:
            return {"error": "winreg is only available on Windows"}
        if root.upper() != "HKCU":
            return {"error": "Only HKCU deletes are allowed"}
        if not confirm:
            return {
                "error": f"This will delete registry key '{key_path}' and all its values. Call again with confirm=true to proceed."
            }
        try:
            winreg.DeleteKey(self._root(root), key_path)
            return {"success": True, "deleted_key": key_path}
        except FileNotFoundError:
            return {"error": f"Key not found: {key_path}"}
        except OSError as e:
            return {"error": f"{e} (key may still have subkeys - delete those first)"}
        except Exception as e:
            return {"error": str(e)}
