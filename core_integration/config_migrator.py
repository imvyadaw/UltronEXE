"""
Config migrator
================
Phase 16 configuration lives in two places that were never actually
merged at runtime:
    1. config.py           - .env-backed constants (GROQ_API_KEY, MODEL_NAME,
                              MAX_TOKENS, storage dirs, voice settings, ...)
    2. config/*.yaml        - default.yaml + a development.yaml/production.yaml
                              overlay, selected by APP_ENV. Every module that
                              references these today (ui/web_ui/app.py,
                              ui/mobile/api/routes.py, scripts/setup.py, ...)
                              just hand-copies the value into a comment
                              ("Mirrors config/default.yaml -> ...") rather
                              than reading the file - there was no loader.

This is that loader, plus a one-way, non-destructive migration into a
single versioned snapshot Phase 17 code can depend on. It never edits
config.py or any config/*.yaml file - it only reads them and writes a
new snapshot under storage/config/. Re-running it is always safe
(idempotent: same inputs -> same snapshot, no accumulating side effects).

Secrets (GROQ_API_KEY, TELEGRAM_BOT_TOKEN, ...) are intentionally left
out of the snapshot - they stay exactly where Phase 16 put them (.env,
read via config.py / os.getenv). The snapshot only carries the
non-secret tuning values config/*.yaml already documents.
"""

import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

try:
    import yaml
except ImportError:
    yaml = None

import config as legacy_config
from utils.helpers import deep_merge

SCHEMA_VERSION = 1

BASE_DIR = Path(__file__).resolve().parent.parent.parent  # Ultron/
CONFIG_DIR = BASE_DIR / "config"
SNAPSHOT_DIR = legacy_config.STORAGE_DIR / "config"
SNAPSHOT_PATH = SNAPSHOT_DIR / "migrated_config.json"
BACKUP_DIR = SNAPSHOT_DIR / "backups"

# Non-secret config.py constants worth carrying into the snapshot.
# Deliberately excludes *_API_KEY / *_TOKEN - those stay in .env only.
_LEGACY_SCALAR_ATTRS = (
    "MODEL_NAME",
    "FALLBACK_MODELS",
    "MAX_TOKENS",
    "TEMPERATURE",
    "TOP_P",
    "MAX_HISTORY_LENGTH",
    "FREE_MODEL_PRIORITY",
    "VECTOR_DB_BACKEND",
    "GEMINI_MODEL",
    "HUGGINGFACE_MODEL",
)


def _load_yaml(path: Path) -> Dict[str, Any]:
    if yaml is None or not path.exists():
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except Exception as e:
        print(f"[config_migrator] Could not parse {path.name}: {e}")
        return {}


def _load_layered_yaml_config() -> Dict[str, Any]:
    """default.yaml, overlaid by {APP_ENV}.yaml if present - same
    deep_merge() helper utils/helpers.py already ships for exactly this,
    just never previously called anywhere."""
    merged = _load_yaml(CONFIG_DIR / "default.yaml")
    env = os.getenv("APP_ENV", "development").strip().lower()
    overlay_path = CONFIG_DIR / f"{env}.yaml"
    if overlay_path.exists():
        merged = deep_merge(merged, _load_yaml(overlay_path))
    return merged


def _legacy_scalars() -> Dict[str, Any]:
    out = {}
    for attr in _LEGACY_SCALAR_ATTRS:
        if hasattr(legacy_config, attr):
            out[attr] = getattr(legacy_config, attr)
    return out


def build_snapshot() -> Dict[str, Any]:
    """Pure function - computes the merged config in memory, doesn't
    touch disk. yaml config wins over config.py on overlapping keys,
    since config/*.yaml is the newer, more granular source (config.py
    itself says as much for AI_MODE mirroring ai.mode)."""
    yaml_layer = _load_layered_yaml_config()
    legacy_layer = {"legacy": _legacy_scalars()}
    merged = deep_merge(legacy_layer, yaml_layer)
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "app_env": os.getenv("APP_ENV", "development").strip().lower(),
        "config": merged,
    }


def migrate(force: bool = False) -> Dict[str, Any]:
    """Writes build_snapshot() to storage/config/migrated_config.json.

    If a snapshot already exists and its config body is unchanged, this
    is a no-op (idempotent) unless force=True. Otherwise the existing
    file is timestamped into storage/config/backups/ before being
    overwritten - migrations are additive, nothing is ever silently lost.
    """
    SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
    new_snapshot = build_snapshot()

    if SNAPSHOT_PATH.exists() and not force:
        try:
            existing = json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))
            if existing.get("config") == new_snapshot["config"]:
                return existing
        except Exception:
            from core.error_trace import log_swallowed as _lsw

            _lsw("core_integration.config_migrator.migrate")

    if SNAPSHOT_PATH.exists():
        BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        shutil.copy2(SNAPSHOT_PATH, BACKUP_DIR / f"migrated_config.{stamp}.json")

    SNAPSHOT_PATH.write_text(json.dumps(new_snapshot, indent=2, default=str), encoding="utf-8")
    return new_snapshot


def get_migrated_config(refresh: bool = False) -> Dict[str, Any]:
    """Read-through accessor: returns the on-disk snapshot, migrating
    first if it doesn't exist yet or refresh=True is passed."""
    if refresh or not SNAPSHOT_PATH.exists():
        return migrate()
    try:
        return json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))
    except Exception:
        return migrate(force=True)


def get_value(dotted_key: str, default: Optional[Any] = None) -> Any:
    """Convenience lookup into the merged config, e.g.
    get_value("ai.model_name") or get_value("legacy.MAX_TOKENS")."""
    snapshot = get_migrated_config()
    node: Any = snapshot.get("config", {})
    for part in dotted_key.split("."):
        if not isinstance(node, dict) or part not in node:
            return default
        node = node[part]
    return node
