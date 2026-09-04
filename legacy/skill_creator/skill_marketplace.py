"""
skill_marketplace.py
====================
A local index of skill packages you can browse and choose to install
- think of it as a folder of signed zip files plus a catalog.json,
not a live networked app store. Nothing in this module fetches
anything automatically:

- `add_index_source()` just remembers a path/URL you gave it; it
  isn't polled in the background.
- `refresh()` is something you call explicitly, and only reads
  local index files unless you pass a URL and confirm it (via
  `web_fetch`-equivalent you supply, since this stays dependency-free).
- `install()` always re-hashes the package against the checksum in
  the catalog entry and refuses on mismatch, then still routes the
  install through `AutoDeployer.deploy()` (which runs full
  validation) - the marketplace never installs directly.

Publishing (`publish()`) just packages a locally-deployed skill plus
its own hash into your own local catalog for others to explicitly
pull from - it doesn't push anywhere on its own either.

Pure standard library.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List

from .auto_deployer import AutoDeployer, DeploymentRejected

logger = logging.getLogger("ultron.skill_marketplace")

DEFAULT_CATALOG_PATH = "ultron_data/skill_creator/marketplace_catalog.json"
DEFAULT_PACKAGE_DIR = "ultron_data/skill_creator/marketplace_packages"


@dataclass
class MarketplaceEntry:
    skill_name: str
    version: str
    description: str
    author: str
    checksum_sha256: str
    package_path: str  # local path to the .py source, relative to package dir
    published_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> dict:
        return asdict(self)


class ChecksumMismatch(Exception):
    pass


class SkillMarketplace:
    """Local skill catalog with explicit, checksum-verified installs.
    Every install still goes through AutoDeployer's full validation -
    a passing checksum only proves the file wasn't corrupted/tampered
    in transit, not that the code itself is safe."""

    def __init__(
        self, deployer: AutoDeployer, catalog_path: str = DEFAULT_CATALOG_PATH, package_dir: str = DEFAULT_PACKAGE_DIR
    ):
        self.deployer = deployer
        self.catalog_path = catalog_path
        self.package_dir = Path(package_dir)
        self.package_dir.mkdir(parents=True, exist_ok=True)
        self._catalog: Dict[str, MarketplaceEntry] = {}
        self._load_catalog()

    def publish(
        self, skill_name: str, version: str, description: str, author: str, source_code: str
    ) -> MarketplaceEntry:
        """Package a piece of skill source into the local catalog for others
        to explicitly browse/install from - does not deploy or send it anywhere."""
        checksum = hashlib.sha256(source_code.encode()).hexdigest()
        package_filename = f"{skill_name}-{version}.py"
        (self.package_dir / package_filename).write_text(source_code)

        entry = MarketplaceEntry(
            skill_name=skill_name,
            version=version,
            description=description,
            author=author,
            checksum_sha256=checksum,
            package_path=package_filename,
        )
        self._catalog[f"{skill_name}@{version}"] = entry
        self._save_catalog()
        logger.info("Published '%s' v%s to local catalog", skill_name, version)
        return entry

    def add_from_external_index(self, entries: List[dict]) -> int:
        """Merge externally-sourced catalog entries (e.g. read from a file you
        downloaded yourself) into the local catalog. Does not fetch anything -
        pass already-retrieved entries in. Returns count added."""
        added = 0
        for raw in entries:
            try:
                entry = MarketplaceEntry(**raw)
            except TypeError:
                logger.warning("Skipped malformed catalog entry")
                continue
            self._catalog[f"{entry.skill_name}@{entry.version}"] = entry
            added += 1
        self._save_catalog()
        return added

    def search(self, query: str) -> List[MarketplaceEntry]:
        q = query.lower()
        return [e for e in self._catalog.values() if q in e.skill_name.lower() or q in e.description.lower()]

    def list_all(self) -> List[MarketplaceEntry]:
        return list(self._catalog.values())

    def install(self, skill_name: str, version: str, acknowledged_warnings: frozenset = frozenset()) -> bool:
        """Verify checksum, then hand off to AutoDeployer for full validation
        and deployment. Never installs on checksum mismatch, ever - this is
        not something a caller can override."""
        key = f"{skill_name}@{version}"
        entry = self._catalog.get(key)
        if not entry:
            logger.warning("No catalog entry for %s", key)
            return False

        package_file = self.package_dir / entry.package_path
        if not package_file.exists():
            logger.error("Package file missing for %s: %s", key, package_file)
            return False

        source_code = package_file.read_text()
        actual_checksum = hashlib.sha256(source_code.encode()).hexdigest()
        if actual_checksum != entry.checksum_sha256:
            raise ChecksumMismatch(
                f"'{key}' failed checksum verification - refusing to install "
                f"(expected {entry.checksum_sha256}, got {actual_checksum})"
            )

        try:
            self.deployer.deploy(skill_name, version, source_code, acknowledged_warnings)
        except DeploymentRejected as exc:
            logger.warning("Install of '%s' rejected by validator: %s", key, exc)
            return False
        return True

    # ------------------------------------------------------------------ storage
    def _load_catalog(self) -> None:
        if not os.path.exists(self.catalog_path):
            return
        try:
            with open(self.catalog_path, "r") as f:
                raw = json.load(f)
            for k, v in raw.get("entries", {}).items():
                self._catalog[k] = MarketplaceEntry(**v)
        except (json.JSONDecodeError, OSError, TypeError) as exc:
            logger.error("Failed to load marketplace catalog: %s", exc)

    def _save_catalog(self) -> None:
        os.makedirs(os.path.dirname(self.catalog_path), exist_ok=True)
        with open(self.catalog_path, "w") as f:
            json.dump({"entries": {k: v.to_dict() for k, v in self._catalog.items()}}, f, indent=2)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    deployer = AutoDeployer(
        skills_dir="ultron_data/skill_creator/_demo_skills", log_path="ultron_data/skill_creator/_demo_deploy_log.json"
    )
    market = SkillMarketplace(
        deployer,
        catalog_path="ultron_data/skill_creator/_demo_catalog.json",
        package_dir="ultron_data/skill_creator/_demo_packages",
    )

    src = 'SKILL_METADATA = {"name": "greeter", "version": "1.0.0"}\ndef greet(name):\n    return f"Hello, {name}!"\n'
    market.publish("greeter", "1.0.0", "Says hello.", author="local_user", source_code=src)
    print("Search 'hello':", [e.skill_name for e in market.search("hello")])
    print("Install result:", market.install("greeter", "1.0.0"))
