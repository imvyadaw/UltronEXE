"""Registry Backup
==================
Export/restore registry keys as JSON snapshots (via RegistryManager's
snapshot_key) and, where `reg.exe` is available, real `.reg` files -
so a risky registry_manager write/delete can always be preceded by a
backup and undone.

Two backup formats, both written under ultron_data/registry_backups/:
  - JSON snapshot (portable, always available, works even without
    reg.exe): produced by RegistryManager.snapshot_key, restored by
    replaying set_value calls through RegistryManager (HKCU only, same
    as every other write path in this package).
  - .reg export/import (native Windows format) via `reg export` /
    `reg import` when reg.exe is on PATH - lets a backup be restored
    with the normal Windows registry editor too, not just ULTRON.

Restore is confirm-gated the same way registry_manager.py's writes are.
"""

import json
import subprocess
import time
from pathlib import Path
from typing import Dict, Optional

from system_control.system_config.registry_manager import RegistryManager, ROOT_KEYS

try:
    HAS_WINREG = True
except ImportError:
    HAS_WINREG = False

BACKUP_DIR = Path("ultron_data") / "registry_backups"


class RegistryBackup:
    """Backup/restore registry keys as JSON snapshots or native .reg files."""

    def __init__(self):
        self._manager = RegistryManager()

    def _ensure_dir(self) -> Path:
        BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        return BACKUP_DIR

    def _safe_name(self, root: str, key_path: str) -> str:
        stem = f"{root.upper()}_{key_path}".replace("\\", "_").replace("/", "_")
        return "".join(c for c in stem if c.isalnum() or c in ("_", "-"))[:150]

    # ----------------------------------------------------------- JSON backup
    def backup_key_json(self, root: str, key_path: str) -> Dict:
        """Snapshot a key (and everything under it) to a timestamped JSON file."""
        snap = self._manager.snapshot_key(root, key_path)
        if not snap.get("success"):
            return snap
        try:
            out_dir = self._ensure_dir()
            fname = f"{self._safe_name(root, key_path)}_{int(time.time())}.json"
            path = out_dir / fname
            path.write_text(json.dumps(snap, indent=2, default=str), encoding="utf-8")
            return {"success": True, "backup_path": str(path), "root": root.upper(), "key_path": key_path}
        except Exception as e:
            return {"error": str(e)}

    def list_backups(self) -> Dict:
        """List backup files (JSON and .reg) previously created."""
        try:
            out_dir = self._ensure_dir()
            files = sorted(out_dir.glob("*"), key=lambda p: p.stat().st_mtime, reverse=True)
            return {"success": True, "backups": [str(f) for f in files], "count": len(files)}
        except Exception as e:
            return {"error": str(e)}

    def restore_key_json(self, backup_path: str, confirm: bool = False) -> Dict:
        """Restore a JSON snapshot by replaying set_value calls. HKCU only
        (same restriction as every write in registry_manager.py) -
        restoring an HKLM backup isn't supported here since it would need
        admin and could affect the whole machine. Confirm-gated."""
        try:
            path = Path(backup_path)
            if not path.exists():
                return {"error": f"Backup file not found: {backup_path}"}
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception as e:
            return {"error": f"Could not read backup: {e}"}

        root = data.get("root")
        key_path = data.get("key_path")
        snapshot = data.get("snapshot")
        if not (root and key_path and snapshot):
            return {"error": "Backup file is missing root/key_path/snapshot"}
        if root.upper() != "HKCU":
            return {"error": "Only HKCU snapshots can be restored (HKLM/etc. need admin)"}

        planned = []

        def _collect(path_str: str, node: Dict):
            if not isinstance(node, dict):
                return
            for v in node.get("values", []) or []:
                planned.append((path_str, v.get("name"), v.get("value")))
            for sub_name, sub_node in (node.get("subkeys") or {}).items():
                _collect(f"{path_str}\\{sub_name}", sub_node)

        _collect(key_path, snapshot)

        if not confirm:
            return {
                "success": False,
                "needs_confirmation": True,
                "preview": f"Would restore {len(planned)} value(s) under {root}\\{key_path} from {backup_path}",
                "message": "Call again with confirm=true to apply.",
            }

        restored, errors = 0, []
        for path_str, name, value in planned:
            if name is None:
                continue
            result = self._manager.set_value(root, path_str, name, value, confirm=True)
            if result.get("success"):
                restored += 1
            else:
                errors.append({"key_path": path_str, "value_name": name, "error": result.get("error")})
        return {"success": len(errors) == 0, "restored": restored, "errors": errors}

    # ------------------------------------------------------------ .reg file
    def export_reg_file(self, root: str, key_path: str, out_path: Optional[str] = None) -> Dict:
        """Export a key to a native .reg file via `reg export` (Windows-only)."""
        if (root or "").upper() not in ROOT_KEYS:
            return {"error": f"Unknown registry root '{root}' - use one of {list(ROOT_KEYS)}"}
        try:
            out_dir = self._ensure_dir()
            full_key = f"{root.upper()}\\{key_path}"
            dest = Path(out_path) if out_path else out_dir / f"{self._safe_name(root, key_path)}_{int(time.time())}.reg"
            result = subprocess.run(
                ["reg", "export", full_key, str(dest), "/y"],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode != 0:
                return {"error": result.stderr.strip() or "reg export failed"}
            return {"success": True, "backup_path": str(dest), "root": root.upper(), "key_path": key_path}
        except FileNotFoundError:
            return {"error": "reg.exe not found - this is only available on Windows"}
        except subprocess.TimeoutExpired:
            return {"error": "reg export timed out"}
        except Exception as e:
            return {"error": str(e)}

    def import_reg_file(self, reg_file_path: str, confirm: bool = False) -> Dict:
        """Import a .reg file via `reg import` (Windows-only). Confirm-gated -
        note reg import applies whatever roots the .reg file itself
        specifies, so double-check the file's contents before confirming."""
        path = Path(reg_file_path)
        if not path.exists():
            return {"error": f".reg file not found: {reg_file_path}"}
        if not confirm:
            return {
                "success": False,
                "needs_confirmation": True,
                "preview": f"Would import registry entries from {reg_file_path} via reg.exe",
                "message": "Call again with confirm=true to apply. Review the file's contents first - "
                "reg import applies whatever roots/keys it contains, not just HKCU.",
            }
        try:
            result = subprocess.run(
                ["reg", "import", str(path)],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode != 0:
                return {"error": result.stderr.strip() or "reg import failed"}
            return {"success": True, "imported_from": str(path)}
        except FileNotFoundError:
            return {"error": "reg.exe not found - this is only available on Windows"}
        except subprocess.TimeoutExpired:
            return {"error": "reg import timed out"}
        except Exception as e:
            return {"error": str(e)}
