"""Application manager
====================
Find, launch, close, and list installed Windows applications.

Speed note: get_installed_apps() used to scan the whole Start Menu tree
(recursive .lnk search) fresh every time apps_cache was empty - and since
Ultron is started/stopped per session (not a long-running daemon), that
in-memory cache reset on every single run, so the FIRST app-open command
of every session paid the full scan cost again. Results are now also
persisted to a small JSON file (APPS_CACHE_FILE) and reused across
process restarts for CACHE_TTL_SECONDS, so only the very first ever run
(or the first run after the cache expires) pays that cost.
"""

import json
import os
import subprocess
import time
import difflib
from pathlib import Path
from typing import Dict, List, Optional

CACHE_TTL_SECONDS = 24 * 60 * 60  # rescan Start Menu at most once a day


def _apps_cache_file() -> Path:
    try:
        from config import CACHE_DIR

        return CACHE_DIR / "installed_apps_cache.json"
    except Exception:
        # config not importable in some contexts (e.g. standalone testing) -
        # fall back to a local file next to this module.
        return Path(__file__).parent / "_installed_apps_cache.json"


# Common app name -> Windows executable / protocol mapping.
# Used as a fallback when there's no matching Start Menu shortcut.
APP_ALIASES = {
    "chrome": "chrome.exe",
    "google chrome": "chrome.exe",
    "edge": "msedge.exe",
    "microsoft edge": "msedge.exe",
    "firefox": "firefox.exe",
    "notepad": "notepad.exe",
    "calculator": "calc.exe",
    "calc": "calc.exe",
    "paint": "mspaint.exe",
    "ms paint": "mspaint.exe",
    "explorer": "explorer.exe",
    "file explorer": "explorer.exe",
    "files": "explorer.exe",
    "cmd": "cmd.exe",
    "command prompt": "cmd.exe",
    "terminal": "cmd.exe",
    "powershell": "powershell.exe",
    "word": "winword.exe",
    "microsoft word": "winword.exe",
    "excel": "excel.exe",
    "microsoft excel": "excel.exe",
    "powerpoint": "powerpnt.exe",
    "microsoft powerpoint": "powerpnt.exe",
    "outlook": "outlook.exe",
    "code": "code",
    "vscode": "code",
    "visual studio code": "code",
    "spotify": "spotify.exe",
    "discord": "discord.exe",
    "telegram": "telegram.exe",
    "whatsapp": "whatsapp.exe",
    "slack": "slack.exe",
    "zoom": "zoom.exe",
    "teams": "teams.exe",
    "microsoft teams": "teams.exe",
    "photoshop": "photoshop.exe",
    "adobe photoshop": "photoshop.exe",
    "settings": "ms-settings:",
    "preferences": "ms-settings:",
    "task manager": "taskmgr.exe",
    "control panel": "control.exe",
}

try:
    import psutil

    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False

try:
    import pygetwindow as gw

    HAS_PYGETWINDOW = True
except ImportError:
    HAS_PYGETWINDOW = False

try:
    import winreg

    HAS_WINREG = True
except ImportError:
    HAS_WINREG = False


class AppManager:
    """Launch, close, and enumerate Windows applications."""

    def __init__(self):
        self.home_dir = Path.home()
        self.apps_cache: Optional[List[str]] = None
        self._shortcut_paths: Dict[str, Path] = {}
        self._app_paths_registry_cache: Optional[Dict[str, str]] = None
        self._appx_cache: Optional[Dict[str, str]] = None
        self._user_app_paths: Optional[Dict[str, str]] = None

    def _start_menu_dirs(self) -> List[Path]:
        return [
            Path(os.environ.get("ProgramData", r"C:\ProgramData"))
            / "Microsoft"
            / "Windows"
            / "Start Menu"
            / "Programs",
            Path(os.environ.get("APPDATA", "")) / "Microsoft" / "Windows" / "Start Menu" / "Programs",
        ]

    def get_installed_apps(self) -> List[str]:
        """Get list of installed applications by scanning Start Menu shortcuts.
        Checks the in-memory cache first, then the on-disk cache (survives
        across Ultron restarts), and only falls back to actually walking
        the Start Menu folders if both are empty/stale."""
        if self.apps_cache is not None:
            return self.apps_cache

        cached = self._load_disk_cache()
        if cached is not None:
            self.apps_cache, self._shortcut_paths = cached
            return self.apps_cache

        apps = []
        self._shortcut_paths = {}
        for start_dir in self._start_menu_dirs():
            if start_dir.exists():
                for item in start_dir.rglob("*.lnk"):
                    apps.append(item.stem)
                    self._shortcut_paths[item.stem] = item

        self.apps_cache = sorted(set(apps))
        self._save_disk_cache()
        return self.apps_cache

    def _load_disk_cache(self):
        """Returns (apps_list, shortcut_paths_dict) if a fresh cache file
        exists, else None. Never raises - a bad/missing cache file just
        means we fall through to a real scan."""
        try:
            path = _apps_cache_file()
            if not path.exists():
                return None
            if time.time() - path.stat().st_mtime > CACHE_TTL_SECONDS:
                return None
            data = json.loads(path.read_text(encoding="utf-8"))
            shortcut_paths = {name: Path(p) for name, p in data.get("shortcut_paths", {}).items()}
            return data.get("apps", []), shortcut_paths
        except Exception:
            return None

    def _save_disk_cache(self):
        """Best-effort - a failure here (e.g. read-only disk) should never
        break app launching, it just means no cache next session."""
        try:
            path = _apps_cache_file()
            path.parent.mkdir(parents=True, exist_ok=True)
            data = {
                "apps": self.apps_cache,
                "shortcut_paths": {name: str(p) for name, p in self._shortcut_paths.items()},
            }
            path.write_text(json.dumps(data), encoding="utf-8")
        except Exception:
            from core.error_trace import log_swallowed as _lsw

            _lsw("windows.apps.manager._save_disk_cache")

    def refresh_installed_apps(self) -> List[str]:
        """Force a fresh Start Menu scan, bypassing both caches - call this
        after installing a new app so Ultron can find it without waiting
        for CACHE_TTL_SECONDS to pass."""
        self.apps_cache = None
        try:
            _apps_cache_file().unlink(missing_ok=True)
        except Exception:
            from core.error_trace import log_swallowed as _lsw

            _lsw("windows.apps.manager.refresh_installed_apps")
        return self.get_installed_apps()

    def _load_user_app_paths(self) -> Dict[str, str]:
        """User-maintained overrides from config/app_paths.json - checked
        FIRST in open_application(), before any auto-detection. Lets you
        pin the exact path for an app that auto-detection can't find
        (custom install location, another drive, a portable app with no
        Start Menu shortcut) so it's guaranteed to open every time.

        Run `python tools/scan_all_apps.py` to auto-populate this file by
        scanning every drive on the machine - or edit it by hand.
        """
        if self._user_app_paths is not None:
            return self._user_app_paths

        self._user_app_paths = {}
        try:
            from config import BASE_DIR

            path = BASE_DIR / "config" / "app_paths.json"
        except Exception:
            path = Path(__file__).resolve().parents[2] / "config" / "app_paths.json"

        try:
            if path.exists():
                data = json.loads(path.read_text(encoding="utf-8"))
                self._user_app_paths = {
                    k.lower().strip(): v
                    for k, v in data.items()
                    if not k.startswith("_") and isinstance(v, str) and v.strip()
                }
        except Exception:
            from core.error_trace import log_swallowed as _lsw

            _lsw("windows.apps.manager._load_user_app_paths")

        return self._user_app_paths

    def find_app(self, query: str) -> Optional[str]:
        """Find an app (Start Menu shortcut name) by partial name match."""
        apps = self.get_installed_apps()
        query_lower = query.lower()

        for app in apps:
            if app.lower() == query_lower:
                return app
        for app in apps:
            if query_lower in app.lower():
                return app
        return None

    def _find_via_app_paths_registry(self, app_name: str) -> Optional[str]:
        """Search the Windows 'App Paths' registry key, which most real
        installers register regardless of whether they also drop a Start
        Menu shortcut. Covers apps get_installed_apps() would otherwise
        miss entirely (e.g. installed for all users under a name that
        doesn't match any .lnk, or with no shortcut at all).

        The full registry walk (HKCU + HKLM, every subkey) is only done
        once per process and cached in memory - previously this re-walked
        both hives from scratch on every single open_application() call
        that reached this step, which is the other big contributor to
        "app open karne mein slow hai" alongside the Start Menu scan."""
        if not HAS_WINREG:
            return None

        if self._app_paths_registry_cache is None:
            self._app_paths_registry_cache = {}
            key_path = r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths"
            for hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
                try:
                    with winreg.OpenKey(hive, key_path) as key:
                        i = 0
                        while True:
                            try:
                                subkey_name = winreg.EnumKey(key, i)
                            except OSError:
                                break
                            i += 1
                            stem = subkey_name.lower().removesuffix(".exe")
                            try:
                                with winreg.OpenKey(key, subkey_name) as subkey:
                                    path, _ = winreg.QueryValueEx(subkey, "")
                                    if path:
                                        self._app_paths_registry_cache[stem] = path
                            except OSError:
                                continue
                except OSError:
                    continue

        query_lower = app_name.lower()
        if query_lower in self._app_paths_registry_cache:
            return self._app_paths_registry_cache[query_lower]
        for stem, path in self._app_paths_registry_cache.items():
            if query_lower in stem:
                return path
        return None

    def _fuzzy_typo_match(self, app_name: str) -> Optional[str]:
        """Catches typos like 'notpad' -> 'notepad' or 'crome' -> 'chrome'
        that exact/substring matching (find_app, APP_ALIASES) both miss.
        Checked as a last resort before giving up entirely, so a real
        unmatched request still ends in 'not found' rather than a wrong
        guess - only a close, high-confidence spelling match is accepted.

        Candidates pool: known aliases, user-pinned overrides, and
        Start Menu shortcut names - i.e. everything Ultron actually knows
        how to open, not just plain dictionary words."""
        query_lower = app_name.lower().strip()
        candidates = set(APP_ALIASES.keys())
        candidates.update(self._load_user_app_paths().keys())
        candidates.update(a.lower() for a in self.get_installed_apps())

        matches = difflib.get_close_matches(query_lower, candidates, n=1, cutoff=0.75)
        return matches[0] if matches else None

    def _find_via_appx_package(self, app_name: str) -> Optional[str]:
        """Find a Microsoft Store (UWP/MSIX) app - e.g. WhatsApp Desktop
        installed from the Store - via PowerShell's Get-AppxPackage.

        Store apps generally do NOT drop a classic Start Menu .lnk file
        the way a normal installer does - they're registered purely via
        their AppxManifest, so get_installed_apps()'s .lnk scan (step 1
        in open_application()) and the App Paths registry (step 3) both
        silently never see them. This is the only reliable way to find +
        launch one. Result is `PackageFamilyName!AppId`, the format
        `explorer.exe shell:AppsFolder\\...` launching expects.

        Only queries the current user's packages (no -AllUsers, which
        needs admin) and is cached in memory for the life of the process -
        the full Get-AppxPackage + per-package manifest walk is slow
        (a few seconds), so it only runs once."""
        if self._appx_cache is None:
            self._appx_cache = {}
            try:
                ps_cmd = (
                    "Get-AppxPackage | ForEach-Object { "
                    "try { $m = Get-AppxPackageManifest $_; "
                    "$appId = $m.Package.Applications.Application.Id; "
                    'if ($appId) { "$($_.Name)|$($_.PackageFamilyName)|$appId" } } catch {} '
                    "}"
                )
                result = subprocess.run(
                    ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_cmd],
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                for line in result.stdout.splitlines():
                    parts = line.strip().split("|")
                    if len(parts) == 3 and all(parts):
                        pkg_name, pfn, app_id = parts
                        self._appx_cache[pkg_name.lower()] = f"{pfn}!{app_id}"
            except Exception:
                from core.error_trace import log_swallowed as _lsw

                _lsw("windows.apps.manager._find_via_appx_package")

        query_lower = app_name.lower().replace(" ", "")
        if query_lower in self._appx_cache:
            return self._appx_cache[query_lower]
        for pkg_name, launch_id in self._appx_cache.items():
            if query_lower in pkg_name:
                return launch_id
        return None

    def open_application(self, app_name: str) -> Dict:
        """Open an application by name (smart matching)."""
        try:
            # 0) User-pinned override (config/app_paths.json) - exact match
            #    first, then substring, so "obs" also matches a key like
            #    "obs studio". Checked before every auto-detection method
            #    below because a path the user typed in themselves should
            #    always win - it's guaranteed correct, unlike a guess.
            user_paths = self._load_user_app_paths()
            query_lower = app_name.lower().strip()
            override_path = user_paths.get(query_lower)
            if not override_path:
                for name, path in user_paths.items():
                    if query_lower in name or name in query_lower:
                        override_path = path
                        break
            if override_path:
                try:
                    os.startfile(override_path)
                    return {"success": True, "opened": app_name, "found_via": "user_override"}
                except OSError:
                    # Path in the file is stale (app moved/uninstalled) -
                    # fall through to auto-detection instead of giving up.
                    from core.error_trace import log_swallowed as _lsw

                    _lsw("windows.apps.manager.open_application")

            # 1) Match a Start Menu shortcut - same as double-clicking it
            shortcut_name = self.find_app(app_name)
            if shortcut_name:
                shortcut_path = self._shortcut_paths.get(shortcut_name)
                if shortcut_path:
                    os.startfile(str(shortcut_path))
                    return {"success": True, "opened": shortcut_name}

            # 2) Known alias -> exe name / protocol (relies on PATH or the
            #    Windows "App Paths" registry, which most installers set up)
            alias = APP_ALIASES.get(app_name.lower())
            if alias:
                try:
                    os.startfile(alias)
                    return {"success": True, "opened": app_name}
                except OSError:
                    from core.error_trace import log_swallowed as _lsw

                    _lsw("windows.apps.manager.open_application")

            # 3) App Paths registry - catches installed apps that have no
            #    Start Menu shortcut and no entry in APP_ALIASES
            registry_path = self._find_via_app_paths_registry(app_name)
            if registry_path:
                try:
                    os.startfile(registry_path)
                    return {"success": True, "opened": app_name}
                except OSError:
                    from core.error_trace import log_swallowed as _lsw

                    _lsw("windows.apps.manager.open_application")

            # 3b) Microsoft Store (UWP/MSIX) app - e.g. WhatsApp Desktop
            #     installed from the Store instead of whatsapp.com's .exe.
            #     Neither step 1 (.lnk scan) nor step 3 (App Paths registry)
            #     ever sees these - see _find_via_appx_package()'s docstring.
            appx_launch_id = self._find_via_appx_package(app_name)
            if appx_launch_id:
                try:
                    subprocess.Popen(["explorer.exe", f"shell:AppsFolder\\{appx_launch_id}"])
                    return {"success": True, "opened": app_name}
                except Exception:
                    from core.error_trace import log_swallowed as _lsw

                    _lsw("windows.apps.manager.open_application")

            # 4) Fuzzy typo correction - e.g. "notpad" -> "notepad",
            #    "crome" -> "chrome". Only a close, high-confidence match
            #    is accepted (see _fuzzy_typo_match's cutoff), so this
            #    doesn't start guessing wildly on genuinely unknown names.
            typo_match = self._fuzzy_typo_match(app_name)
            if typo_match and typo_match != app_name.lower():
                corrected = self.open_application(typo_match)
                if corrected.get("success"):
                    corrected["corrected_from"] = app_name
                    return corrected

            # 5) Last resort: try the raw name directly
            try:
                os.startfile(app_name)
                return {"success": True, "opened": app_name}
            except OSError:
                from core.error_trace import log_swallowed as _lsw

                _lsw("windows.apps.manager.open_application")

            apps = self.get_installed_apps()
            similar = [a for a in apps if app_name.lower() in a.lower()][:5]
            if not similar:
                close = difflib.get_close_matches(app_name.lower(), [a.lower() for a in apps], n=5, cutoff=0.5)
                similar = close
            return {
                "success": False,
                "error": f"App '{app_name}' not found",
                "similar_apps": similar,
                "fix": (
                    f'Add "{app_name.lower()}": "<exact path to its .exe>" to '
                    "config/app_paths.json, or run tools/scan_all_apps.py to "
                    "auto-detect it - then it will always open."
                ),
            }

        except Exception as e:
            return {"error": str(e)}

    def _fuzzy_running_process(self, app_name: str) -> Optional[str]:
        """When the app name doesn't map to a known alias, look at what's
        actually running right now and fuzzy-match against real process
        names - covers apps spoken about loosely ('close discord') where
        the real exe differs (e.g. an Electron app with a versioned or
        oddly-cased process name)."""
        if not HAS_PSUTIL:
            return None
        query_lower = app_name.lower()
        try:
            names = {p.info["name"] for p in psutil.process_iter(["name"]) if p.info["name"]}
        except Exception:
            return None
        for name in names:
            if name.lower() == query_lower or name.lower() == query_lower + ".exe":
                return name
        for name in names:
            if query_lower in name.lower():
                return name
        return None

    def close_application(self, app_name: str) -> Dict:
        """Close an application by process name."""
        try:
            exe_name = APP_ALIASES.get(app_name.lower(), app_name)
            if not exe_name.lower().endswith(".exe"):
                exe_name += ".exe"

            # Graceful close first (sends WM_CLOSE to the app's windows)
            result = subprocess.run(["taskkill", "/IM", exe_name], capture_output=True, text=True, timeout=10)
            if result.returncode == 0:
                return {"success": True, "closed": app_name}

            # Force close if graceful close didn't work
            result = subprocess.run(["taskkill", "/IM", exe_name, "/F"], capture_output=True, text=True, timeout=10)
            if result.returncode == 0:
                return {"success": True, "closed": app_name, "forced": True}

            # Neither worked with the guessed exe name (probably wrong for
            # this app) - fuzzy-match against actually running processes
            # and retry once with the real name.
            real_name = self._fuzzy_running_process(app_name)
            if real_name and real_name.lower() != exe_name.lower():
                result = subprocess.run(["taskkill", "/IM", real_name], capture_output=True, text=True, timeout=10)
                if result.returncode == 0:
                    return {"success": True, "closed": real_name}
                result = subprocess.run(
                    ["taskkill", "/IM", real_name, "/F"], capture_output=True, text=True, timeout=10
                )
                if result.returncode == 0:
                    return {"success": True, "closed": real_name, "forced": True}

            return {"success": False, "error": result.stderr.strip() or f"'{app_name}' does not appear to be running"}

        except Exception as e:
            return {"error": str(e)}

    def list_running_apps(self) -> Dict:
        """List currently running applications (visible windows)."""
        if HAS_PYGETWINDOW:
            try:
                titles = [t for t in gw.getAllTitles() if t.strip()]
                return {"running_apps": titles, "count": len(titles)}
            except Exception as e:
                return {"error": str(e)}

        if HAS_PSUTIL:
            names = sorted(set(p.info["name"] for p in psutil.process_iter(["name"]) if p.info["name"]))
            return {"running_apps": names, "count": len(names)}

        return {"error": "pygetwindow/psutil not installed - run: pip install pygetwindow psutil"}


# Process-wide shared instance. Previously every consumer (app_manager.py,
# app_finder.py, app_detector.py, app_launcher.py, skills/windows/manager.py,
# windows/__init__.py, apps/base_app.py) constructed its own `AppManager()`
# in its own __init__ - harmless on its own (the constructor does no I/O),
# but it meant each one's in-memory apps_cache started empty, so the first
# get_installed_apps() call from EACH of those 6-7 call sites independently
# hit the on-disk cache file (or, worst case, independently re-walked the
# Start Menu) instead of sharing one already-warm result. get_app_manager()
# gives every caller the same instance so that work happens at most once
# per process. Existing direct `AppManager()` construction still works
# exactly as before for any caller that genuinely wants an isolated
# instance - this is additive, not a replacement.
_shared_app_manager: Optional["AppManager"] = None


def get_app_manager() -> "AppManager":
    global _shared_app_manager
    if _shared_app_manager is None:
        _shared_app_manager = AppManager()
    return _shared_app_manager
