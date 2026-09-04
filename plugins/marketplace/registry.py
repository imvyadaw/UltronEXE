"""
Plugin marketplace
===================
A local catalog of plugins Ultron knows how to install, plus a minimal
"install" flow that scaffolds a new plugins/installed/<name>/plugin.py
stub matching plugins/sdk/base.py's UltronPlugin interface (see
plugins/installed/telegram/ for a real, hand-written example).

The catalog is a JSON file next to this module rather than a live
remote registry - Ultron is meant to run fully offline, so "browsing
the marketplace" here means browsing a maintained local list, and
"installing" means generating the boilerplate for the user (or a
future contributor) to fill in, exactly like plugins/loader.py already
expects to find.
"""

import json
from pathlib import Path
from typing import Dict, List

CATALOG_PATH = Path(__file__).resolve().parent / "catalog.json"
INSTALLED_DIR = Path(__file__).resolve().parents[1] / "installed"

_DEFAULT_CATALOG = [
    {
        "name": "telegram",
        "description": "Control Ultron remotely via Telegram messages.",
        "version": "1.0.0",
        "requires_config": ["TELEGRAM_BOT_TOKEN"],
        "built_in": True,
    },
    {
        "name": "discord",
        "description": "Control Ultron remotely via a Discord bot.",
        "version": "0.1.0",
        "requires_config": ["DISCORD_BOT_TOKEN"],
        "built_in": False,
    },
    {
        "name": "slack",
        "description": "Control Ultron remotely via a Slack app.",
        "version": "0.1.0",
        "requires_config": ["SLACK_BOT_TOKEN", "SLACK_APP_TOKEN"],
        "built_in": False,
    },
]

_STUB_TEMPLATE = '''"""
{name} plugin
{underline}
Scaffolded by plugins/marketplace/registry.py. Fill in register()
with whatever this plugin needs to do at startup.
"""
from plugins.sdk.base import UltronPlugin


class {class_name}Plugin(UltronPlugin):
    name = "{name}"

    def register(self, brain) -> None:
        print("[{name} plugin] registered - implement me in plugins/installed/{name}/plugin.py")


PLUGIN = {class_name}Plugin()
'''


class PluginMarketplace:
    """Browse and install plugins from the local catalog."""

    def __init__(self):
        if not CATALOG_PATH.exists():
            CATALOG_PATH.write_text(json.dumps(_DEFAULT_CATALOG, indent=2), encoding="utf-8")

    def _load_catalog(self) -> List[Dict]:
        try:
            return json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
        except Exception:
            return _DEFAULT_CATALOG

    def list_available(self) -> Dict:
        """List every plugin in the catalog."""
        catalog = self._load_catalog()
        installed_names = {p.name for p in INSTALLED_DIR.glob("*") if p.is_dir()}
        for entry in catalog:
            entry["installed"] = entry["name"] in installed_names
        return {"count": len(catalog), "plugins": catalog}

    def search(self, query: str) -> Dict:
        """Search catalog entries by name/description substring."""
        query_l = query.lower()
        matches = [
            p
            for p in self._load_catalog()
            if query_l in p["name"].lower() or query_l in p.get("description", "").lower()
        ]
        return {"query": query, "count": len(matches), "results": matches}

    def get_plugin_info(self, name: str) -> Dict:
        for entry in self._load_catalog():
            if entry["name"] == name:
                return entry
        return {"error": f"No plugin named '{name}' in the catalog"}

    def install(self, name: str) -> Dict:
        """Scaffold plugins/installed/<name>/plugin.py from the catalog
        entry. Does not download/execute remote code - Ultron has no
        network install path by design; this just generates the stub a
        human fills in, the same shape as the hand-written telegram
        plugin."""
        info = self.get_plugin_info(name)
        if "error" in info:
            return info

        plugin_dir = INSTALLED_DIR / name
        if plugin_dir.exists():
            return {"error": f"Plugin '{name}' is already installed at {plugin_dir}"}

        try:
            plugin_dir.mkdir(parents=True)
            (plugin_dir / "__init__.py").write_text("", encoding="utf-8")
            class_name = "".join(part.capitalize() for part in name.split("_"))
            stub = _STUB_TEMPLATE.format(name=name, underline="=" * (len(name) + 8), class_name=class_name)
            (plugin_dir / "plugin.py").write_text(stub, encoding="utf-8")
            return {
                "success": True,
                "name": name,
                "path": str(plugin_dir),
                "requires_config": info.get("requires_config", []),
                "next_step": "Fill in register() in plugin.py, then restart Ultron to auto-discover it.",
            }
        except Exception as e:
            return {"error": str(e)}

    def uninstall(self, name: str) -> Dict:
        """Remove an installed plugin's directory."""
        plugin_dir = INSTALLED_DIR / name
        if not plugin_dir.exists():
            return {"error": f"Plugin '{name}' is not installed"}
        try:
            import shutil

            shutil.rmtree(plugin_dir)
            return {"success": True, "removed": name}
        except Exception as e:
            return {"error": str(e)}
