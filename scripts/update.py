#!/usr/bin/env python3
"""
scripts/update.py - pull the latest changes and reinstall dependencies.

Runs (skipping any step that doesn't apply):
  1. `git pull` - only if root/.git exists. Skipped with a message
     otherwise (e.g. a checkout that isn't a git clone).
  2. `pip install -r <file>` for every requirements file found at the
     project root and under ui/ (currently just ui/requirements-ui.txt -
     there's no top-level requirements.txt in this checkout yet).

Usage:
    python scripts/update.py
    python scripts/update.py --skip-git
    python scripts/update.py --skip-install
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


def project_root() -> Path:
    return Path(__file__).resolve().parent.parent


def find_requirements_files(root: Path) -> list[Path]:
    candidates = [root / "requirements.txt", root / "ui" / "requirements-ui.txt"]
    return [p for p in candidates if p.exists()]


def git_pull(root: Path, runner=subprocess.run) -> dict:
    if not (root / ".git").exists():
        return {"ran": False, "reason": "not a git checkout (no .git/)"}

    result = runner(
        ["git", "-C", str(root), "pull"],
        capture_output=True,
        text=True,
        check=False,
    )
    return {
        "ran": True,
        "returncode": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
    }


def pip_install(requirements_files: list[Path], runner=subprocess.run) -> list[dict]:
    results = []
    for req_file in requirements_files:
        result = runner(
            [sys.executable, "-m", "pip", "install", "-r", str(req_file)],
            capture_output=True,
            text=True,
            check=False,
        )
        results.append(
            {
                "file": req_file,
                "returncode": result.returncode,
                "stdout": result.stdout,
                "stderr": result.stderr,
            }
        )
    return results


def run(
    root: Path | None = None,
    skip_git: bool = False,
    skip_install: bool = False,
    runner=subprocess.run,
) -> dict:
    root = root or project_root()

    git_result = None if skip_git else git_pull(root, runner=runner)

    install_results = []
    if not skip_install:
        install_results = pip_install(find_requirements_files(root), runner=runner)

    return {"git": git_result, "installs": install_results}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=None)
    parser.add_argument("--skip-git", action="store_true")
    parser.add_argument("--skip-install", action="store_true")
    args = parser.parse_args()

    result = run(args.root, skip_git=args.skip_git, skip_install=args.skip_install)

    if result["git"] is None:
        print("Skipped git pull.")
    elif not result["git"]["ran"]:
        print(f"Skipped git pull: {result['git']['reason']}")
    else:
        print(result["git"]["stdout"].strip() or "(git pull produced no output)")
        if result["git"]["returncode"] != 0:
            print(f"git pull failed (exit {result['git']['returncode']}):\n{result['git']['stderr']}")

    if not result["installs"]:
        print("No requirements files installed (skipped, or none found).")
    for install in result["installs"]:
        status = "ok" if install["returncode"] == 0 else f"failed (exit {install['returncode']})"
        print(f"pip install -r {install['file']}: {status}")
        if install["returncode"] != 0:
            print(install["stderr"])


if __name__ == "__main__":
    sys.exit(main())
