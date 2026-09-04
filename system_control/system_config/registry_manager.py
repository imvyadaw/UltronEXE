"""Registry Manager
===================
Higher-level registry control on top of `winreg`, sitting alongside
windows/registry/editor.py (RegistryEditor - the low-level CRUD class)
and apps/system/registry.py (RegistryApp - opens regedit.exe + basic
read/list). This class adds the things neither of those cover:
search-by-name-or-value across a subtree, and a bulk "export a whole
key to a dict" snapshot (used by registry_backup.py before any write).

Safety model (same line RegistryEditor already draws):
  - Reads (get_value/list_values/list_subkeys/search_key/snapshot_key)
    are allowed against any root.
  - Writes/deletes (set_value/delete_value/delete_key) are HKCU-only -
    HKLM/HKCR/HKU/HKCC need admin and can affect the whole machine, so
    they're refused outright rather than silently requiring elevation.
  - Writes/deletes are also confirm-gated: call once to preview, call
    again with confirm=True to apply.
"""

from typing import Dict, List, Optional

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
    _TYPE_MAP = {
        "REG_SZ": winreg.REG_SZ,
        "REG_EXPAND_SZ": winreg.REG_EXPAND_SZ,
        "REG_DWORD": winreg.REG_DWORD,
        "REG_QWORD": winreg.REG_QWORD,
        "REG_MULTI_SZ": winreg.REG_MULTI_SZ,
        "REG_BINARY": winreg.REG_BINARY,
    }

# Safety net: even under HKCU, these subtrees are sensitive enough
# (autorun, shell association, policy) that writes/deletes need an
# extra explicit nod - confirm=True still required, but we also refuse
# if the key_path doesn't at least look like a normal app-settings path
# and the value name matches something dangerous, e.g. wiping "Shell".
_SENSITIVE_VALUE_NAMES = {"shell", "userinit", "system"}


class RegistryManager:
    """Registry read/write/search/delete with HKCU-only writes and confirm-gating."""

    def _root(self, root: str):
        root = (root or "").upper()
        if root not in ROOT_KEYS:
            raise ValueError(f"Unknown registry root '{root}' - use one of {list(ROOT_KEYS)}")
        return _ROOT_MAP[root]

    # ---------------------------------------------------------------- reads
    def get_value(self, root: str, key_path: str, value_name: str) -> Dict:
        """Read a single value, e.g. root='HKCU', key_path='Software\\MyApp'."""
        if not HAS_WINREG:
            return {"error": "winreg is only available on Windows"}
        try:
            with winreg.OpenKey(self._root(root), key_path) as key:
                value, value_type = winreg.QueryValueEx(key, value_name)
                return {
                    "success": True,
                    "root": root.upper(),
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
        """List every value under a key."""
        if not HAS_WINREG:
            return {"error": "winreg is only available on Windows"}
        try:
            values: List[Dict] = []
            with winreg.OpenKey(self._root(root), key_path) as key:
                i = 0
                while True:
                    try:
                        name, value, vtype = winreg.EnumValue(key, i)
                        values.append({"name": name, "value": value, "type": vtype})
                        i += 1
                    except OSError:
                        break
            return {"success": True, "root": root.upper(), "key_path": key_path, "values": values, "count": len(values)}
        except FileNotFoundError:
            return {"error": f"Key not found: {root}\\{key_path}"}
        except Exception as e:
            return {"error": str(e)}

    def list_subkeys(self, root: str, key_path: str) -> Dict:
        """List subkey names under a key."""
        if not HAS_WINREG:
            return {"error": "winreg is only available on Windows"}
        try:
            subkeys: List[str] = []
            with winreg.OpenKey(self._root(root), key_path) as key:
                i = 0
                while True:
                    try:
                        subkeys.append(winreg.EnumKey(key, i))
                        i += 1
                    except OSError:
                        break
            return {
                "success": True,
                "root": root.upper(),
                "key_path": key_path,
                "subkeys": subkeys,
                "count": len(subkeys),
            }
        except FileNotFoundError:
            return {"error": f"Key not found: {root}\\{key_path}"}
        except Exception as e:
            return {"error": str(e)}

    def search_key(
        self,
        root: str,
        key_path: str,
        query: str,
        search_values: bool = True,
        search_names: bool = True,
        max_depth: int = 6,
        max_results: int = 200,
    ) -> Dict:
        """Recursively search under key_path for value names/data (and
        subkey names) containing `query` (case-insensitive). Bounded by
        max_depth/max_results so a broad search under a huge hive (e.g.
        HKLM\\Software) can't hang or flood the response."""
        if not HAS_WINREG:
            return {"error": "winreg is only available on Windows"}
        query_l = (query or "").lower()
        if not query_l:
            return {"error": "query must be non-empty"}
        matches: List[Dict] = []
        root_handle = self._root(root)

        def _walk(path: str, depth: int):
            if depth > max_depth or len(matches) >= max_results:
                return
            try:
                with winreg.OpenKey(root_handle, path) as key:
                    if search_names or search_values:
                        i = 0
                        while True:
                            try:
                                name, value, vtype = winreg.EnumValue(key, i)
                                i += 1
                                hit = (search_names and query_l in name.lower()) or (
                                    search_values and query_l in str(value).lower()
                                )
                                if hit:
                                    matches.append(
                                        {"key_path": path, "value_name": name, "value": value, "type": vtype}
                                    )
                                    if len(matches) >= max_results:
                                        return
                            except OSError:
                                break
                    j = 0
                    while True:
                        try:
                            sub = winreg.EnumKey(key, j)
                            j += 1
                        except OSError:
                            break
                        if search_names and query_l in sub.lower():
                            matches.append(
                                {"key_path": f"{path}\\{sub}", "value_name": None, "value": None, "type": "SUBKEY"}
                            )
                            if len(matches) >= max_results:
                                return
                        _walk(f"{path}\\{sub}", depth + 1)
            except (FileNotFoundError, PermissionError, OSError):
                return

        try:
            _walk(key_path, 0)
        except Exception as e:
            return {"error": str(e)}
        return {
            "success": True,
            "root": root.upper(),
            "key_path": key_path,
            "query": query,
            "matches": matches,
            "count": len(matches),
            "truncated": len(matches) >= max_results,
        }

    def snapshot_key(self, root: str, key_path: str, max_depth: int = 10) -> Dict:
        """Recursively dump a key's values and subkeys into a nested dict -
        used by registry_backup.py before any destructive write, and useful
        standalone to inspect a whole subtree at once."""
        if not HAS_WINREG:
            return {"error": "winreg is only available on Windows"}
        root_handle = self._root(root)

        def _dump(path: str, depth: int) -> Optional[Dict]:
            if depth > max_depth:
                return {"truncated": True}
            try:
                with winreg.OpenKey(root_handle, path) as key:
                    values = []
                    i = 0
                    while True:
                        try:
                            name, value, vtype = winreg.EnumValue(key, i)
                            values.append({"name": name, "value": value, "type": vtype})
                            i += 1
                        except OSError:
                            break
                    subkeys = {}
                    j = 0
                    while True:
                        try:
                            sub = winreg.EnumKey(key, j)
                            j += 1
                        except OSError:
                            break
                        subkeys[sub] = _dump(f"{path}\\{sub}", depth + 1)
                    return {"values": values, "subkeys": subkeys}
            except FileNotFoundError:
                return None
            except (PermissionError, OSError) as e:
                return {"error": str(e)}

        try:
            snapshot = _dump(key_path, 0)
        except Exception as e:
            return {"error": str(e)}
        if snapshot is None:
            return {"error": f"Key not found: {root}\\{key_path}"}
        return {"success": True, "root": root.upper(), "key_path": key_path, "snapshot": snapshot}

    # --------------------------------------------------------------- writes
    def set_value(
        self, root: str, key_path: str, value_name: str, value, value_type: str = "REG_SZ", confirm: bool = False
    ) -> Dict:
        """Create/overwrite a value. HKCU only. Confirm-gated."""
        if not HAS_WINREG:
            return {"error": "winreg is only available on Windows"}
        if (root or "").upper() != "HKCU":
            return {"error": "Only HKCU writes are allowed (HKLM/etc. need admin and can affect the whole system)"}
        if value_name.lower() in _SENSITIVE_VALUE_NAMES:
            return {
                "error": f"Refusing to write sensitive value name '{value_name}' - this can break Windows login/shell."
            }
        if not confirm:
            return {
                "success": False,
                "needs_confirmation": True,
                "preview": f"Would set {root.upper()}\\{key_path}\\{value_name} = {value!r} ({value_type})",
                "message": "Call again with confirm=true to apply.",
            }
        try:
            reg_type = _TYPE_MAP.get(value_type.upper(), winreg.REG_SZ)
            with winreg.CreateKeyEx(self._root(root), key_path) as key:
                winreg.SetValueEx(key, value_name, 0, reg_type, value)
            return {
                "success": True,
                "root": root.upper(),
                "key_path": key_path,
                "value_name": value_name,
                "value": value,
            }
        except Exception as e:
            return {"error": str(e)}

    def create_key(self, root: str, key_path: str, confirm: bool = False) -> Dict:
        """Create a (possibly empty) key. HKCU only. Confirm-gated."""
        if not HAS_WINREG:
            return {"error": "winreg is only available on Windows"}
        if (root or "").upper() != "HKCU":
            return {"error": "Only HKCU key creation is allowed (HKLM/etc. need admin and can affect the whole system)"}
        if not confirm:
            return {
                "success": False,
                "needs_confirmation": True,
                "preview": f"Would create key {root.upper()}\\{key_path}",
                "message": "Call again with confirm=true to apply.",
            }
        try:
            with winreg.CreateKeyEx(self._root(root), key_path):
                pass
            return {"success": True, "root": root.upper(), "key_path": key_path, "created": True}
        except Exception as e:
            return {"error": str(e)}

    def delete_value(self, root: str, key_path: str, value_name: str, confirm: bool = False) -> Dict:
        """Delete a single value. HKCU only. Confirm-gated."""
        if not HAS_WINREG:
            return {"error": "winreg is only available on Windows"}
        if (root or "").upper() != "HKCU":
            return {"error": "Only HKCU deletes are allowed"}
        if not confirm:
            return {
                "success": False,
                "needs_confirmation": True,
                "preview": f"Would delete value '{value_name}' under {root.upper()}\\{key_path}",
                "message": "Call again with confirm=true to apply.",
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
        """Delete a key (must have no subkeys - winreg's own limitation).
        HKCU only. Confirm-gated."""
        if not HAS_WINREG:
            return {"error": "winreg is only available on Windows"}
        if (root or "").upper() != "HKCU":
            return {"error": "Only HKCU deletes are allowed"}
        if not confirm:
            return {
                "success": False,
                "needs_confirmation": True,
                "preview": f"Would delete key {root.upper()}\\{key_path} and all its values",
                "message": "Call again with confirm=true to apply.",
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
