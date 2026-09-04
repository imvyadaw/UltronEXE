#!/usr/bin/env python3
"""
scripts/backup.py - manual point-in-time snapshot of Ultron's SQLite
databases, per storage/backups/README.md.

Finds every *.db file under storage/ (wherever core ends up putting
memory.db, vault.db, audit_log.db, etc. - none of those modules are
present in this checkout yet, so this is a no-op until they exist)
and copies it into storage/backups/<timestamp>/, preserving relative
path so files with the same name from different subdirs don't clash.

Explicitly skips storage/backups/ itself (don't back up backups) and
storage/secure/ - per the README, the encryption key + auth salt in
there need their own, more careful backup process; this script
deliberately does not touch it.

Usage:
    python scripts/backup.py
    python scripts/backup.py --root /path/to/Ultron
"""

from __future__ import annotations

import argparse
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

EXCLUDED_SUBDIRS = {"backups", "secure"}


def project_root() -> Path:
    return Path(__file__).resolve().parent.parent


def find_databases(storage_dir: Path) -> list[Path]:
    found = []
    for db_path in storage_dir.rglob("*.db"):
        try:
            relative_top = db_path.relative_to(storage_dir).parts[0]
        except (ValueError, IndexError):
            continue
        if relative_top in EXCLUDED_SUBDIRS:
            continue
        found.append(db_path)
    return sorted(found)


def run(root: Path | None = None, timestamp: str | None = None) -> dict:
    root = root or project_root()
    storage_dir = root / "storage"
    backups_dir = storage_dir / "backups"
    timestamp = timestamp or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    snapshot_dir = backups_dir / timestamp

    databases = find_databases(storage_dir)
    copied = []

    if databases:
        snapshot_dir.mkdir(parents=True, exist_ok=True)
        for db_path in databases:
            rel = db_path.relative_to(storage_dir)
            dest = snapshot_dir / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(db_path, dest)
            copied.append(dest)

    return {"snapshot_dir": snapshot_dir if copied else None, "copied": copied}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=None)
    args = parser.parse_args()

    result = run(args.root)

    if not result["copied"]:
        print("No *.db files found under storage/ (excluding backups/ and secure/) - nothing to back up.")
        return

    print(f"Backed up {len(result['copied'])} database file(s) to {result['snapshot_dir']}:")
    for dest in result["copied"]:
        print(f"  - {dest}")


if __name__ == "__main__":
    sys.exit(main())
