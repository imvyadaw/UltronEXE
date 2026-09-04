"""App finder
==========
Locates applications beyond what a plain Start Menu shortcut scan
finds: fuzzy/partial name search with a relevance score, category
lookup (browser/editor/media/...), and a filesystem sweep of the
common install directories (Program Files, Program Files (x86),
AppData\\Local\\Programs) for the actual .exe when nothing else matches.
"""

import os
from pathlib import Path
from typing import Dict, Optional

from windows.apps.manager import get_app_manager

# Rough category buckets, keyed by lowercase keyword found in the app name.
# Used for "open a browser" / "close all media apps" style requests where
# the person doesn't name a specific app.
APP_CATEGORIES = {
    "browser": ["chrome", "edge", "firefox", "opera", "brave", "safari"],
    "editor": ["code", "notepad", "sublime", "atom", "pycharm", "intellij", "vim", "word", "winword"],
    "media": ["spotify", "vlc", "itunes", "music", "netflix", "youtube"],
    "communication": ["discord", "slack", "teams", "zoom", "telegram", "whatsapp", "skype", "outlook"],
    "office": ["word", "excel", "powerpoint", "outlook", "onenote"],
    "utility": ["calculator", "notepad", "paint", "explorer", "cmd", "powershell", "terminal"],
    "development": ["code", "pycharm", "intellij", "visual studio", "git", "docker", "terminal", "cmd", "powershell"],
    "creative": ["photoshop", "illustrator", "premiere", "figma", "blender", "paint"],
}

# Common per-machine install roots to sweep when Start Menu + registry both miss.
_INSTALL_ROOTS = [
    os.environ.get("ProgramFiles", r"C:\Program Files"),
    os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"),
    str(Path.home() / "AppData" / "Local" / "Programs"),
    str(Path.home() / "AppData" / "Local"),
]


class AppFinder:
    """Fuzzy/category app lookup, plus a filesystem sweep for stray .exe files."""

    def __init__(self):
        self._apps = get_app_manager()

    def find(self, query: str) -> Dict:
        """Best-effort single match: Start Menu shortcut -> App Paths registry
        -> filesystem sweep. Returns the match plus how it was found."""
        try:
            shortcut = self._apps.find_app(query)
            if shortcut:
                return {"success": True, "name": shortcut, "found_via": "start_menu"}

            reg_path = self._apps._find_via_app_paths_registry(query)
            if reg_path:
                return {"success": True, "name": query, "path": reg_path, "found_via": "registry"}

            exe_path = self.find_executable(query)
            if exe_path:
                return {"success": True, "name": query, "path": exe_path, "found_via": "filesystem"}

            return {"success": False, "error": f"No app matching '{query}' found"}
        except Exception as e:
            return {"error": str(e)}

    def find_executable(self, name: str) -> Optional[str]:
        """Sweep common install directories for a matching .exe. Slow-ish
        (walks a few directory trees) so only used as a last resort."""
        query_lower = name.lower().replace(" ", "")
        for root in _INSTALL_ROOTS:
            root_path = Path(root)
            if not root_path.exists():
                continue
            try:
                for dirpath, _dirnames, filenames in os.walk(root_path):
                    # Don't recurse too deep - install dirs are shallow in practice
                    depth = len(Path(dirpath).relative_to(root_path).parts)
                    if depth > 3:
                        continue
                    for fname in filenames:
                        if not fname.lower().endswith(".exe"):
                            continue
                        stem = fname[:-4].lower().replace(" ", "")
                        if query_lower == stem or query_lower in stem:
                            return str(Path(dirpath) / fname)
            except (PermissionError, OSError):
                continue
        return None

    def search(self, query: str, limit: int = 10) -> Dict:
        """Return every installed app whose name contains the query, ranked
        with exact/startswith matches first."""
        try:
            apps = self._apps.get_installed_apps()
            query_lower = query.lower()

            def score(app_name: str) -> int:
                lower = app_name.lower()
                if lower == query_lower:
                    return 0
                if lower.startswith(query_lower):
                    return 1
                if query_lower in lower:
                    return 2
                return 3

            matches = [a for a in apps if query_lower in a.lower()]
            matches.sort(key=score)
            return {"query": query, "matches": matches[:limit], "count": len(matches)}
        except Exception as e:
            return {"error": str(e)}

    def list_by_category(self, category: str) -> Dict:
        """List installed apps that fall into a known category (browser,
        editor, media, communication, office, utility, development, creative)."""
        category = category.lower()
        keywords = APP_CATEGORIES.get(category)
        if not keywords:
            return {"error": f"Unknown category '{category}'", "known_categories": list(APP_CATEGORIES.keys())}
        try:
            apps = self._apps.get_installed_apps()
            matches = [a for a in apps if any(k in a.lower() for k in keywords)]
            return {"category": category, "apps": matches, "count": len(matches)}
        except Exception as e:
            return {"error": str(e)}

    def categorize(self, app_name: str) -> Dict:
        """Guess which category a given app name belongs to."""
        lower = app_name.lower()
        for category, keywords in APP_CATEGORIES.items():
            if any(k in lower for k in keywords):
                return {"app_name": app_name, "category": category}
        return {"app_name": app_name, "category": "unknown"}
