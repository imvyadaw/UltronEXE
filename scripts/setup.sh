#!/usr/bin/env bash
# scripts/setup.sh - thin wrapper so `./scripts/setup.sh` works on
# Linux/macOS the same way `scripts\setup.bat` does on Windows.
# All real logic lives in scripts/setup.py (idempotent, safe to re-run).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"

PYTHON_BIN="${PYTHON_BIN:-python3}"
if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
    PYTHON_BIN=python
fi

exec "$PYTHON_BIN" "$SCRIPT_DIR/setup.py" --root "$ROOT_DIR" "$@"
