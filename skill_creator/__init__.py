"""
SKILL_CREATOR
=============
A pipeline for turning "ULTRON, learn to do X" into a real, reviewed
skill module: read an API's docs -> generate a scaffold -> run it in
a locked-down sandbox -> statically validate it -> deploy it only
after that validation passes -> optionally share/install skills via
a local, checksum-verified marketplace.

Every stage is a checkpoint, not a rubber stamp:
- `sandbox_tester` runs candidate code with no filesystem/network/
  subprocess access and a hard wall-clock timeout.
- `skill_validator` statically rejects dangerous constructs (eval,
  exec, os.system, subprocess with shell=True, dynamic imports,
  arbitrary network calls) unless a human explicitly whitelists them
  for a specific, reviewed skill.
- `auto_deployer` will not install anything that hasn't passed
  validation, and always keeps the previous version for rollback.
- `skill_marketplace` never auto-installs; every install is a
  human-confirmed action against a checksum-verified package.
"""

from .api_doc_reader import APIDocReader, APIEndpoint
from .skill_code_generator import SkillCodeGenerator, SkillSpec
from .sandbox_tester import SandboxTester, SandboxResult
from .skill_validator import SkillValidator, ValidationReport, Severity as ValidationSeverity
from .auto_deployer import AutoDeployer, DeploymentRecord
from .skill_marketplace import SkillMarketplace, MarketplaceEntry

__all__ = [
    "APIDocReader",
    "APIEndpoint",
    "SkillCodeGenerator",
    "SkillSpec",
    "SandboxTester",
    "SandboxResult",
    "SkillValidator",
    "ValidationReport",
    "ValidationSeverity",
    "AutoDeployer",
    "DeploymentRecord",
    "SkillMarketplace",
    "MarketplaceEntry",
]
