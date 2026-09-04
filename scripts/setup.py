#!/usr/bin/env python3
"""
scripts/setup.py - first-run setup for a fresh checkout.

What it does (all idempotent - safe to re-run):
  1. Creates the storage/ subdirectories listed under `storage:` in
     config/default.yaml, if they don't already exist.
  2. Copies config/secrets.yaml.template -> config/secrets.yaml if the
     latter doesn't exist yet (never overwrites an existing one).
  3. Prints what still needs manual attention (filling in secrets.yaml,
     installing ui/requirements-ui.txt).

Usage:
    python scripts/setup.py
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

# Mirrors config/default.yaml's `storage:` block.
STORAGE_SUBDIRS = ["cache", "logs", "backups", "exports", "temp", "secure"]


def project_root() -> Path:
    return Path(__file__).resolve().parent.parent


def ensure_storage_dirs(root: Path) -> list[Path]:
    created = []
    storage_dir = root / "storage"
    for name in STORAGE_SUBDIRS:
        d = storage_dir / name
        if not d.exists():
            d.mkdir(parents=True, exist_ok=True)
            created.append(d)
    return created


def ensure_secrets_file(root: Path) -> Path | None:
    template = root / "config" / "secrets.yaml.template"
    target = root / "config" / "secrets.yaml"
    if target.exists():
        return None
    if not template.exists():
        return None
    shutil.copyfile(template, target)
    return target


def run(root: Path | None = None) -> dict:
    root = root or project_root()
    created_dirs = ensure_storage_dirs(root)
    secrets_created = ensure_secrets_file(root)
    return {"created_dirs": created_dirs, "secrets_created": secrets_created}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        type=Path,
        default=None,
        help="Project root (defaults to the repo this script lives in)",
    )
    args = parser.parse_args()

    result = run(args.root)

    if result["created_dirs"]:
        print("Created storage directories:")
        for d in result["created_dirs"]:
            print(f"  - {d}")
    else:
        print("storage/ subdirectories already present, nothing to create.")

    if result["secrets_created"]:
        print(f"\nCreated {result['secrets_created']} from secrets.yaml.template.")
        print("Fill in real values before enabling any integration that needs them.")
    else:
        print("\nconfig/secrets.yaml already exists (or no template found) - left untouched.")

    print("\nNext steps:")
    print("  pip install -r ui/requirements-ui.txt   # if you want the web UI / mobile API")
    print("  python -m ui.web_ui.app                 # then run it")


if __name__ == "__main__":
    sys.exit(main())
