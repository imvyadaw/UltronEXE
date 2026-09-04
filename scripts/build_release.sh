#!/usr/bin/env bash
# build_release.sh — builds a clean, secret-free ULTRON release ZIP.
# Fails loudly instead of silently shipping secrets or runtime state.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

OUT_NAME="${1:-ultron_release_$(date +%Y%m%d_%H%M%S).zip}"
STAGE_DIR="$(mktemp -d)"
echo "[build_release] staging in $STAGE_DIR"

# 1. Copy everything except VCS metadata into the staging dir.
rsync -a --exclude='.git' ./ "$STAGE_DIR/"

# 2. Strip secrets, runtime DBs, caches, logs from the staged copy only.
find "$STAGE_DIR" -iname ".env" -delete
find "$STAGE_DIR" -iname "*.env.local" -delete
find "$STAGE_DIR" -iname "*.db" -delete
find "$STAGE_DIR" -iname "*.sqlite" -delete
find "$STAGE_DIR" -iname "*.sqlite3" -delete
find "$STAGE_DIR" -iname "__pycache__" -type d -prune -exec rm -rf {} +
find "$STAGE_DIR" -iname "*.pyc" -delete
find "$STAGE_DIR" -path "*/storage/cache/*.json" -delete
find "$STAGE_DIR" -path "*/logs/*.log" -delete

# 3. Hard-fail secret scan before we ever zip anything up.
echo "[build_release] scanning staged tree for leftover secrets/DBs..."
FOUND=0

if find "$STAGE_DIR" -iname ".env" | grep -q .; then
  echo "  BLOCKED: .env still present in staged build"
  FOUND=1
fi

if find "$STAGE_DIR" \( -iname "*.db" -o -iname "*.sqlite*" \) | grep -q .; then
  echo "  BLOCKED: runtime database file(s) still present:"
  find "$STAGE_DIR" \( -iname "*.db" -o -iname "*.sqlite*" \)
  FOUND=1
fi

# Simple heuristic secret grep for anything that slipped through as a
# tracked file (e.g. a committed key rather than .env). Looks for common
# API key/token patterns in non-.example files.
if grep -RInE "(api[_-]?key|secret|token)\s*=\s*['\"]?[A-Za-z0-9_\-]{20,}" \
    --include="*.py" --include="*.json" --include="*.yaml" --include="*.yml" \
    "$STAGE_DIR" 2>/dev/null | grep -v "\.env\.example" | grep -q .; then
  echo "  WARNING: possible hardcoded secret found in source — review before shipping:"
  grep -RInE "(api[_-]?key|secret|token)\s*=\s*['\"]?[A-Za-z0-9_\-]{20,}" \
    --include="*.py" --include="*.json" --include="*.yaml" --include="*.yml" \
    "$STAGE_DIR" 2>/dev/null | grep -v "\.env\.example"
  FOUND=1
fi

if [ "$FOUND" -ne 0 ]; then
  echo "[build_release] ABORTED — fix the above before building a release ZIP."
  rm -rf "$STAGE_DIR"
  exit 1
fi

# 4. Zip it up.
mkdir -p "$ROOT/dist"
( cd "$STAGE_DIR" && zip -qr "$ROOT/dist/$OUT_NAME" . )
rm -rf "$STAGE_DIR"

echo "[build_release] OK — clean release built at dist/$OUT_NAME"
