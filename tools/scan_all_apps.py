"""
Scan every drive for installed apps and fill config/app_paths.json
====================================================================
open_application() already checks Start Menu shortcuts, the Windows
"App Paths" registry, and Microsoft Store packages - but all three only
ever see apps installed the normal way on the C: drive. A lot of real
laptops (especially anything set up for gaming) have apps, games, and
portable tools installed on D:, E:, etc. with no Start Menu shortcut at
all - those come back as "not found" no matter how good the C:-drive
detection is.

This script sweeps EVERY drive letter that exists on the machine for
.exe files, and writes any app it finds straight into
config/app_paths.json under a lowercase key = the exe's own name.
open_application() checks that file FIRST, before any auto-detection,
so once an app shows up here it will always open - no more guessing.

Usage:
    python tools/scan_all_apps.py

Safe to re-run any time (e.g. after installing something new) - it
only ADDS new entries, it never touches or overwrites anything already
in the file, whether you added it by hand or a previous scan did.
"""

import json
import os
import platform
import string
import sys
import time
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
APP_PATHS_FILE = BASE_DIR / "config" / "app_paths.json"

# Every one of these substrings appearing in a filename means "this is
# not the app itself" - installers, uninstallers, updaters, redistributables,
# crash handlers, etc. Skipping them keeps the result to actual apps you'd
# ask Ultron to open, instead of hundreds of junk entries.
_SKIP_SUBSTRINGS = [
    "uninstall",
    "unins0",
    "setup",
    "installer",
    "vc_redist",
    "vcredist",
    "update",
    "updater",
    "crashpad",
    "crashreporter",
    "crash_handler",
    "helper",
    "service",
    "daemon",
    "elevat",
    "repair",
    "bootstrap",
    "redist",
    "dotnetfx",
    "directx",
    "dxsetup",
    "wisptis",
]

# Folders that are either huge, irrelevant, or both - skipping them is
# what keeps a full-drive scan from taking forever.
_SKIP_DIR_NAMES = {
    "windows",
    "$recycle.bin",
    "system volume information",
    "node_modules",
    ".git",
    "package cache",
    "programdata",
    "temp",
    "tmp",
    "cache",
    "$windows.~bt",
    "$windows.~ws",
    "recovery",
    "perflogs",
    "windowsapps",  # Store apps are handled separately, via winreg/PowerShell
}

MAX_DEPTH = 6  # how many folders deep to go under each drive root
PROGRESS_EVERY = 2000  # print a "still scanning" line every N directories


def _available_drives():
    if platform.system() != "Windows":
        return []
    drives = []
    for letter in string.ascii_uppercase:
        root = f"{letter}:\\"
        try:
            if os.path.exists(root):
                drives.append(root)
        except OSError:
            continue
    return drives


def _is_junk(stem_lower: str) -> bool:
    return any(s in stem_lower for s in _SKIP_SUBSTRINGS)


def _scan_drive(root: str, found: dict, scanned_dirs: list):
    root_path = Path(root)
    for dirpath, dirnames, filenames in os.walk(root_path):
        # Prune skip-listed / too-deep directories in place so os.walk
        # doesn't descend into them at all.
        rel_depth = len(Path(dirpath).relative_to(root_path).parts)
        if rel_depth >= MAX_DEPTH:
            dirnames[:] = []
            continue
        dirnames[:] = [d for d in dirnames if d.lower() not in _SKIP_DIR_NAMES]

        scanned_dirs.append(1)
        if len(scanned_dirs) % PROGRESS_EVERY == 0:
            print(f"  ...scanning, {len(scanned_dirs)} folders checked so far " f"(currently in {dirpath})")

        for fname in filenames:
            if not fname.lower().endswith(".exe"):
                continue
            stem = fname[:-4]
            stem_lower = stem.lower()
            if _is_junk(stem_lower) or len(stem_lower) < 3:
                continue
            full_path = str(Path(dirpath) / fname)
            # Keep the shortest path for a given name - the top-level
            # install location, not some nested cache/backup copy of the
            # same exe that a couple of apps ship internally.
            existing = found.get(stem_lower)
            if existing is None or len(full_path) < len(existing):
                found[stem_lower] = full_path


def main():
    if platform.system() != "Windows":
        print("This scan is Windows-only (it looks for drive letters + .exe files).")
        sys.exit(1)

    drives = _available_drives()
    print(f"Found {len(drives)} drive(s): {', '.join(drives)}")
    print(
        "Scanning for .exe files (this can take a couple of minutes on a " "full drive, especially the first time)...\n"
    )

    found = {}
    scanned_dirs = []
    start = time.time()
    for drive in drives:
        print(f"Scanning {drive} ...")
        try:
            _scan_drive(drive, found, scanned_dirs)
        except Exception as e:
            print(f"  Skipped {drive} after an error: {e}")

    elapsed = time.time() - start
    print(
        f"\nScan finished in {elapsed:.0f}s - {len(scanned_dirs)} folders checked, "
        f"{len(found)} candidate apps found."
    )

    # Load the existing file (if any) and only add names it doesn't
    # already have - never touch or overwrite an existing entry, whether
    # it was added by hand or by an earlier run of this script.
    existing_data = {}
    if APP_PATHS_FILE.exists():
        try:
            existing_data = json.loads(APP_PATHS_FILE.read_text(encoding="utf-8"))
        except Exception:
            print(
                f"Warning: {APP_PATHS_FILE} exists but isn't valid JSON - "
                "starting fresh instead of risking your existing entries."
            )
            existing_data = {}

    added = 0
    for name, path in found.items():
        if name not in existing_data:
            existing_data[name] = path
            added += 1

    APP_PATHS_FILE.parent.mkdir(parents=True, exist_ok=True)
    APP_PATHS_FILE.write_text(json.dumps(existing_data, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"\nAdded {added} new app path(s) to {APP_PATHS_FILE}")
    print(f"Total entries in the file now: " f"{len([k for k in existing_data if not k.startswith('_')])}")
    if added:
        print(
            "\nUltron will pick these up on its next run - no restart of " "this script needed, just relaunch main.py."
        )


if __name__ == "__main__":
    main()
