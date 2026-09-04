"""
Plugin versioning
=================
Tracks which version of each installed plugin is running, keeps a
history of version changes, and checks installed versions against
plugins/marketplace's catalog for available updates. Backed by SQLite,
same pattern as the rest of Ultron's persistence layer.
"""

import sqlite3
import time
from pathlib import Path
from typing import Dict

DB_PATH = Path(__file__).resolve().parents[2] / "storage" / "sqlite" / "plugin_versions.db"


class PluginVersionManager:
    """Record and query installed plugin versions."""

    def __init__(self):
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
        self._conn.execute("""CREATE TABLE IF NOT EXISTS current_versions (
                plugin_name TEXT PRIMARY KEY,
                version TEXT,
                installed_at REAL
            )""")
        self._conn.execute("""CREATE TABLE IF NOT EXISTS version_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                plugin_name TEXT,
                from_version TEXT,
                to_version TEXT,
                changed_at REAL
            )""")
        self._conn.commit()

    def record_version(self, plugin_name: str, version: str) -> Dict:
        """Record the currently-installed version of a plugin, logging
        a history entry if it's changing from a prior version."""
        try:
            cur = self._conn.cursor()
            cur.execute("SELECT version FROM current_versions WHERE plugin_name = ?", (plugin_name,))
            row = cur.fetchone()
            previous = row[0] if row else None

            cur.execute(
                "INSERT INTO current_versions (plugin_name, version, installed_at) VALUES (?, ?, ?) "
                "ON CONFLICT(plugin_name) DO UPDATE SET version = excluded.version, installed_at = excluded.installed_at",
                (plugin_name, version, time.time()),
            )
            if previous and previous != version:
                cur.execute(
                    "INSERT INTO version_history (plugin_name, from_version, to_version, changed_at) VALUES (?, ?, ?, ?)",
                    (plugin_name, previous, version, time.time()),
                )
            self._conn.commit()
            return {"success": True, "plugin_name": plugin_name, "version": version, "previous_version": previous}
        except Exception as e:
            return {"error": str(e)}

    def get_version(self, plugin_name: str) -> Dict:
        try:
            cur = self._conn.cursor()
            cur.execute("SELECT version, installed_at FROM current_versions WHERE plugin_name = ?", (plugin_name,))
            row = cur.fetchone()
            if not row:
                return {"error": f"No recorded version for '{plugin_name}'"}
            return {"plugin_name": plugin_name, "version": row[0], "installed_at": row[1]}
        except Exception as e:
            return {"error": str(e)}

    def history(self, plugin_name: str) -> Dict:
        """Full version-change history for a plugin, oldest first."""
        try:
            cur = self._conn.cursor()
            cur.execute(
                "SELECT from_version, to_version, changed_at FROM version_history WHERE plugin_name = ? ORDER BY changed_at",
                (plugin_name,),
            )
            rows = cur.fetchall()
            changes = [{"from_version": r[0], "to_version": r[1], "changed_at": r[2]} for r in rows]
            return {"plugin_name": plugin_name, "count": len(changes), "history": changes}
        except Exception as e:
            return {"error": str(e)}

    def check_for_update(self, plugin_name: str) -> Dict:
        """Compare the installed version against plugins/marketplace's
        catalog entry for the plugin."""
        installed = self.get_version(plugin_name)
        if "error" in installed:
            return installed
        try:
            from plugins.marketplace.registry import PluginMarketplace

            catalog_entry = PluginMarketplace().get_plugin_info(plugin_name)
            if "error" in catalog_entry:
                return {
                    "plugin_name": plugin_name,
                    "installed_version": installed["version"],
                    "update_available": None,
                    "note": "Not found in marketplace catalog",
                }
            latest = catalog_entry.get("version")
            return {
                "plugin_name": plugin_name,
                "installed_version": installed["version"],
                "latest_version": latest,
                "update_available": latest is not None and latest != installed["version"],
            }
        except Exception as e:
            return {"error": str(e)}

    def rollback(self, plugin_name: str) -> Dict:
        """Report the previous version to roll back to (this module tracks
        version metadata only - actually swapping the plugin's code back
        is left to plugins/marketplace.install() with that version, since
        this store doesn't keep old code snapshots)."""
        history = self.history(plugin_name)
        if "error" in history or not history["history"]:
            return {"error": f"No version history to roll back for '{plugin_name}'"}
        previous = history["history"][-1]["from_version"]
        return {
            "plugin_name": plugin_name,
            "rollback_to_version": previous,
            "note": "Version metadata only - reinstall that version's code manually or via marketplace.",
        }
