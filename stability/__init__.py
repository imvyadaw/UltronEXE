"""
PHASE 29-A - Stability layer
=============================
Sits underneath integration (which answers "is this build GO/NO-GO
to ship") and addresses the class of problem that shows up *before* a
pipeline test even gets to run: an eager heavy/optional import breaking a
whole composing module, no single place to register shutdown cleanup, and
no guardrail against a response claiming a tool action succeeded when it
didn't.

    lazy_loader          - defer heavy/optional third-party imports to first use
    dependency_validator  - cheap (non-importing) report of what's installed
    exception_hardening   - import one component in isolation; don't let it
                             take a whole composing module down
    resource_cleanup      - one process-wide registry for shutdown cleanup
    truth_prompt_contract - system-prompt addendum + runtime check that a
                             response's claims match what tools reported

Also fixes, in the existing codebase, the two concrete instances of the
eager-heavy-import problem that integration's README had already
flagged: agents/coding_agent.py's `from groq import Groq` and
vision/object_detection/yolo_detector.py's `from ultralytics import YOLO`,
both now deferred via lazy_loader.

See README.md in this directory for the full writeup, and run_phase29a.py
for the validation suite (compile / unit / integration / dependency tests).
"""

from stability.lazy_loader import LazyImport, lazy_module, lazy_attr, registry_status
from stability.dependency_validator import validate as validate_dependencies, DependencyReport
from stability.exception_hardening import safe_import_component, failed_components
from stability.resource_cleanup import register_cleanup, shutdown_all
from stability.truth_prompt_contract import TRUTH_CONTRACT_ADDENDUM, check_turn

__all__ = [
    "LazyImport",
    "lazy_module",
    "lazy_attr",
    "registry_status",
    "validate_dependencies",
    "DependencyReport",
    "safe_import_component",
    "failed_components",
    "register_cleanup",
    "shutdown_all",
    "TRUTH_CONTRACT_ADDENDUM",
    "check_turn",
]
