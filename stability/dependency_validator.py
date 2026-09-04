"""
Dependency validation
======================
Answers "what's actually installed in this environment?" *before* anything
tries to use a package, using `importlib.util.find_spec()` - which locates a
module without executing it, so checking for `torch`/`ultralytics` here
costs milliseconds, not the multi-second cost of actually importing them.

This is deliberately narrower than `core/startup.py`'s checks (which cover
config, DB connectivity, etc.) - it only answers the dependency-presence
question, split into:

- REQUIRED: the app cannot run at all without these.
- OPTIONAL: individual features degrade (already handled gracefully by
  their own module, per integration's README) if these are
  missing, but nothing should crash on import because of them.

`core/startup.py` already had a not-quite-comparable dependency check baked
into its combined report; this module is the more granular piece
`deploy_check.py` and `lazy_loader.py`'s registry can both build on, and is
safe to call as often as needed (no caching surprises, no side effects).
"""

from __future__ import annotations

import importlib.metadata as _im
import importlib.util
import sys
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from stability.lazy_loader import registry_status


# Known cross-package version conflicts worth flagging explicitly, beyond
# plain "is it installed". Each entry: (package, constraint_desc, checker)
# where checker(installed_version: str) -> bool (True = OK, False = conflict).
# A2: gTTS pins click<8.2,>=7.1; flask>=3.0 pins click>=8.1.3. The only
# range that satisfies both is 8.1.3-8.1.x - if click resolves outside
# that (e.g. a bare `pip install click` after the fact, or an unrelated
# package dragging in click>=8.2), gTTS's CLI/import breaks in a way that
# `find_spec("gtts")` alone would never catch (the package is present,
# just incompatible).
def _click_ok(version: str) -> bool:
    try:
        parts = tuple(int(p) for p in version.split(".")[:2])
    except ValueError:
        return True  # unparsable version string - don't false-positive
    return (8, 1) <= parts < (8, 2)


VERSION_CONFLICTS = {
    "click": (
        "gTTS needs click<8.2,>=7.1; flask>=3.0 needs click>=8.1.3 " "- only click 8.1.x satisfies both",
        _click_ok,
    ),
}

# Packages the app cannot function without at all.
REQUIRED = [
    "json",  # stdlib sanity check - if this fails, the interpreter itself is broken
]

# Packages that back individual optional features. Keyed by the feature
# name a human would recognize, so a report reads "voice (tts): missing"
# rather than just a bare package name.
OPTIONAL: Dict[str, str] = {
    "groq": "cloud LLM (coding agent, cloud chat backend)",
    "openai": "cloud LLM (alternate backend)",
    "anthropic": "cloud LLM (alternate backend)",
    "elevenlabs": "voice (cloud TTS)",
    "ultralytics": "vision (YOLO object detection - also pulls in torch)",
    "torch": "vision/ML (backing ultralytics and any local model inference)",
    "cv2": "vision (face detection, OCR preprocessing - opencv-python)",
    "chromadb": "memory (vector DB backend)",
    "faiss": "memory (alternate vector DB backend)",
    "dotenv": "config (.env file loading)",
}


def _find(module_name: str) -> bool:
    try:
        return importlib.util.find_spec(module_name) is not None
    except (ImportError, ValueError, ModuleNotFoundError):
        # find_spec can itself raise if a parent package is broken/half-installed;
        # that means "not usably available", same as not found.
        return False


@dataclass
class DependencyReport:
    required_ok: bool
    missing_required: List[str] = field(default_factory=list)
    optional: Dict[str, bool] = field(default_factory=dict)
    missing_optional: Dict[str, str] = field(default_factory=dict)
    python_version: str = field(default_factory=lambda: sys.version.split()[0])
    lazy_registry: Dict[str, dict] = field(default_factory=dict)
    incompatible: Dict[str, str] = field(default_factory=dict)

    def summary(self) -> str:
        lines = [f"Dependency report (python {self.python_version})"]
        lines.append("  required: " + ("OK" if self.required_ok else f"MISSING {self.missing_required}"))
        if self.missing_optional:
            lines.append("  optional missing (features will degrade, not crash):")
            for pkg, feature in sorted(self.missing_optional.items()):
                lines.append(f"    - {pkg}: {feature}")
        else:
            lines.append("  optional: all present")
        if self.incompatible:
            lines.append("  VERSION CONFLICTS (installed but incompatible with each other):")
            for pkg, detail in sorted(self.incompatible.items()):
                lines.append(f"    - {pkg}: {detail}")
        if self.lazy_registry:
            lines.append("  lazily-imported so far this process:")
            for name, status in sorted(self.lazy_registry.items()):
                lines.append(f"    - {name}: {status}")
        return "\n".join(lines)


def _installed_version(package: str) -> Optional[str]:
    try:
        return _im.version(package)
    except _im.PackageNotFoundError:
        return None


def check_version_conflicts() -> Dict[str, str]:
    """Cheap (metadata-only, no import) check for known cross-package
    version pins that can both be individually 'installed' per
    find_spec() yet still be mutually incompatible (see VERSION_CONFLICTS
    above) - the gap plain presence-checking can't see."""
    problems: Dict[str, str] = {}
    for pkg, (detail, checker) in VERSION_CONFLICTS.items():
        version = _installed_version(pkg)
        if version is not None and not checker(version):
            problems[pkg] = f"installed={version} - {detail}"
    return problems


def validate() -> DependencyReport:
    """Run the full required+optional check. Never raises - a missing
    required dependency is reported, not thrown, so callers (deploy_check,
    a health endpoint, a CLI) decide what to do with a NO-GO themselves."""
    missing_required = [m for m in REQUIRED if not _find(m)]
    optional_status = {pkg: _find(pkg) for pkg in OPTIONAL}
    missing_optional = {pkg: feature for pkg, feature in OPTIONAL.items() if not optional_status[pkg]}
    return DependencyReport(
        required_ok=not missing_required,
        missing_required=missing_required,
        optional=optional_status,
        missing_optional=missing_optional,
        lazy_registry=registry_status(),
        incompatible=check_version_conflicts(),
    )


if __name__ == "__main__":
    print(validate().summary())
