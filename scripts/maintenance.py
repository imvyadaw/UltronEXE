#!/usr/bin/env python3
"""
scripts/maintenance.py - routine housekeeping.

What it does:
  1. Clears storage/temp/ and storage/cache/temp/ - per their READMEs,
     both are "safe to clear" scratch space, nothing there is expected
     to survive a restart. Leaves each dir's .gitkeep/README.md in
     place.
  2. Prints a quick size summary of each storage/ subdirectory, so
     it's obvious if backups/ or exports/ are quietly growing.

Does NOT touch storage/backups/, storage/exports/, or storage/secure/ -
those are durable/user-facing (or sensitive) per their own READMEs.

Usage:
    python scripts/maintenance.py
    python scripts/maintenance.py --dry-run
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PRESERVED_IN_TEMP = {".gitkeep", "README.md"}


def project_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _clear_dir(temp_dir: Path, dry_run: bool = False) -> list[Path]:
    if not temp_dir.exists():
        return []

    removed = []
    for entry in sorted(temp_dir.iterdir()):
        if entry.name in PRESERVED_IN_TEMP:
            continue
        removed.append(entry)
        if dry_run:
            continue
        if entry.is_dir():
            import shutil

            shutil.rmtree(entry)
        else:
            entry.unlink()
    return removed


def clear_temp(storage_dir: Path, dry_run: bool = False) -> list[Path]:
    removed = _clear_dir(storage_dir / "temp", dry_run=dry_run)
    removed += _clear_dir(storage_dir / "cache" / "temp", dry_run=dry_run)
    return removed


def dir_size(path: Path) -> int:
    if not path.exists():
        return 0
    return sum(f.stat().st_size for f in path.rglob("*") if f.is_file())


def storage_summary(storage_dir: Path) -> dict[str, int]:
    if not storage_dir.exists():
        return {}
    return {d.name: dir_size(d) for d in sorted(storage_dir.iterdir()) if d.is_dir()}


def human_size(num_bytes: int) -> str:
    size = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024:
            return f"{size:.1f}{unit}"
        size /= 1024
    return f"{size:.1f}TB"


def run(root: Path | None = None, dry_run: bool = False) -> dict:
    root = root or project_root()
    storage_dir = root / "storage"
    removed = clear_temp(storage_dir, dry_run=dry_run)
    summary = storage_summary(storage_dir)
    return {"removed_from_temp": removed, "summary": summary}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=None)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report what would be removed without deleting anything",
    )
    args = parser.parse_args()

    result = run(args.root, dry_run=args.dry_run)

    verb = "Would remove" if args.dry_run else "Removed"
    if result["removed_from_temp"]:
        print(f"{verb} {len(result['removed_from_temp'])} item(s) from storage/temp/:")
        for entry in result["removed_from_temp"]:
            print(f"  - {entry.name}")
    else:
        print("storage/temp/ already empty.")

    print("\nstorage/ usage:")
    for name, size in result["summary"].items():
        print(f"  {name:10s} {human_size(size)}")


if __name__ == "__main__":
    sys.exit(main())
