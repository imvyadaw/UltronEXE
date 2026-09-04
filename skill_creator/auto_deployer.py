"""
auto_deployer.py
====================
The only module in this package allowed to write a skill into the
live `skills/` directory ULTRON actually loads from. It will refuse
to do that unless:

1. `SkillValidator.validate()` reports no CRITICAL findings, and
2. any WARNING findings have been explicitly acknowledged by name
   (passed in as `acknowledged_warnings`) - there's no "deploy
   anyway" flag that skips this, short of not calling validate in the
   first place, which `deploy()` does internally so that can't be
   bypassed by a caller forgetting to.

Every deploy keeps the previous version on disk under `_versions/` so
`rollback()` always has somewhere to go back to. Nothing here reaches
out to a network marketplace on its own - see `skill_marketplace.py`
for that, which is a separate, human-confirmed step.

Pure standard library.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Set

from .skill_validator import SkillValidator, ValidationReport

logger = logging.getLogger("ultron.auto_deployer")

DEFAULT_SKILLS_DIR = "ultron_data/skill_creator/skills"
DEFAULT_LOG_PATH = "ultron_data/skill_creator/deployment_log.json"
# Caps in-memory + on-disk log growth over long-running sessions (was
# unbounded before - a 24/7 session doing frequent skill deployments would
# have grown this list forever).
MAX_LOG_ENTRIES = 500


@dataclass
class DeploymentRecord:
    skill_name: str
    version: str
    deployed_at: str = field(default_factory=lambda: datetime.now().isoformat())
    validation_summary: str = ""
    rolled_back: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


class DeploymentRejected(Exception):
    """Raised when validation fails and the caller tries to deploy anyway."""


class AutoDeployer:
    def __init__(
        self,
        skills_dir: str = DEFAULT_SKILLS_DIR,
        log_path: str = DEFAULT_LOG_PATH,
        validator: Optional[SkillValidator] = None,
    ):
        self.skills_dir = Path(skills_dir)
        self.versions_dir = self.skills_dir / "_versions"
        self.log_path = log_path
        self.validator = validator or SkillValidator()
        self._log: List[dict] = []
        self.skills_dir.mkdir(parents=True, exist_ok=True)
        self.versions_dir.mkdir(parents=True, exist_ok=True)
        self._load_log()

    def dry_run(self, source_code: str, acknowledged_warnings: Set[str] = frozenset()) -> ValidationReport:
        """Validate without touching disk - use this to show the user what
        would happen before they confirm a real deploy."""
        return self.validator.validate(source_code, acknowledged_warnings)

    def deploy(
        self, skill_name: str, version: str, source_code: str, acknowledged_warnings: Set[str] = frozenset()
    ) -> DeploymentRecord:
        """Validate then write the skill file. Raises DeploymentRejected if
        validation finds anything CRITICAL or an unacknowledged WARNING."""
        report = self.validator.validate(source_code, acknowledged_warnings)

        if report.has_critical:
            raise DeploymentRejected(f"blocked by critical finding(s):\n{report.summary()}")
        if report.has_unacknowledged_warnings:
            raise DeploymentRejected(
                f"blocked by unacknowledged warning(s) - review and pass their names in "
                f"acknowledged_warnings if you've confirmed they're fine:\n{report.summary()}"
            )

        target_path = self.skills_dir / f"{skill_name}.py"
        if target_path.exists():
            self._archive_current(skill_name)

        target_path.write_text(source_code)
        record = DeploymentRecord(skill_name=skill_name, version=version, validation_summary=report.summary())
        self._append_log(record)
        logger.info("Deployed skill '%s' v%s", skill_name, version)
        return record

    def rollback(self, skill_name: str) -> bool:
        """Restore the most recently archived version of a skill."""
        archive_dir = self.versions_dir / skill_name
        if not archive_dir.exists():
            logger.warning("No archived version to roll back to for '%s'", skill_name)
            return False

        archives = sorted(archive_dir.glob("*.py"), reverse=True)
        if not archives:
            return False

        latest_archive = archives[0]
        shutil.copy(latest_archive, self.skills_dir / f"{skill_name}.py")
        latest_archive.unlink()

        for entry in reversed(self._log):
            if entry["skill_name"] == skill_name and not entry["rolled_back"]:
                entry["rolled_back"] = True
                break
        self._save_log()
        logger.info("Rolled back skill '%s' to previous version", skill_name)
        return True

    def deployed_skills(self) -> List[str]:
        return sorted(p.stem for p in self.skills_dir.glob("*.py"))

    def history(self, skill_name: Optional[str] = None) -> List[dict]:
        if skill_name:
            return [e for e in self._log if e["skill_name"] == skill_name]
        return list(self._log)

    # ------------------------------------------------------------------ internal
    def _archive_current(self, skill_name: str) -> None:
        current = self.skills_dir / f"{skill_name}.py"
        archive_dir = self.versions_dir / skill_name
        archive_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        shutil.copy(current, archive_dir / f"{stamp}.py")

    def _append_log(self, record: DeploymentRecord) -> None:
        self._log.append(record.to_dict())
        self._log = self._log[-MAX_LOG_ENTRIES:]
        self._save_log()

    def _load_log(self) -> None:
        if not os.path.exists(self.log_path):
            return
        try:
            with open(self.log_path, "r") as f:
                self._log = json.load(f).get("entries", [])
        except (json.JSONDecodeError, OSError):
            self._log = []

    def _save_log(self) -> None:
        os.makedirs(os.path.dirname(self.log_path), exist_ok=True)
        with open(self.log_path, "w") as f:
            json.dump({"entries": self._log}, f, indent=2)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    deployer = AutoDeployer(
        skills_dir="ultron_data/skill_creator/_demo_skills", log_path="ultron_data/skill_creator/_demo_deploy_log.json"
    )

    good_code = 'SKILL_METADATA = {"name": "demo", "version": "0.1.0"}\ndef ping():\n    return "pong"\n'
    print(deployer.deploy("demo_skill", "0.1.0", good_code))

    bad_code = 'import os\ndef wipe():\n    os.system("rm -rf /")\n'
    try:
        deployer.deploy("evil_skill", "0.1.0", bad_code)
    except DeploymentRejected as exc:
        print("Correctly rejected:", exc)
