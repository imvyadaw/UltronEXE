"""
Exception hardening - subsystem import/init isolation
========================================================
Two exception-handling layers already exist and are staying exactly as
they are:

- `core/error_handler.py`'s `ErrorHandler.run_safely()` - per tool *call*,
  with retry/classification.
- `integration/error_hardening.py`'s circuit breaker - per
  *context*, trips after repeated failures across many calls.

Both assume the callable itself is reachable, i.e. the module it lives in
already imported successfully. Phase 29's own README documents a gap one
level up: `windows/__init__.py` composes ~25 submodules with a flat list of
top-level imports, so *one* broken/uninstalled-dependency submodule
(`agents/coding_agent.py` needing `groq`, before the lazy_loader.py fix)
took down the *entire* `windows` package, and therefore every tool that
doesn't even touch that submodule.

`safe_import_component()` below is that missing layer: import one component
in isolation, catch anything (ImportError, or any exception a badly-behaved
module raises at import time), log it once, and return `None` instead of
letting it propagate - so a composing module (like `windows/__init__.py`)
can build its facade from whatever components *did* come up, the same
"degrade, don't crash" way `core/startup.py` treats subsystem checks.

This does not replace fixing eager heavy imports with `lazy_loader.py` -
that's still the right fix when the failure is a genuinely optional/heavy
dependency, since it avoids paying the import cost at all until needed.
`safe_import_component()` is the backstop for everything else: a typo, a
missing local file, a submodule that isn't optional-dependency-related but
is still broken in this particular checkout.
"""

from __future__ import annotations

import importlib
import traceback
from typing import Any, Optional

try:
    from core.logger import get_logger

    _logger = get_logger("ultron.stability.exception_hardening")
except Exception:  # pragma: no cover
    import logging

    _logger = logging.getLogger("ultron.stability.exception_hardening")

_failed_components: dict = {}


def safe_import_component(module_path: str, attr_name: Optional[str] = None) -> Optional[Any]:
    """Import `module_path` (optionally pulling one attribute off it) and
    return it, or return None and log a warning instead of raising.

    Example - the pattern windows/__init__.py's top-of-file imports should
    move to for anything not already covered by lazy_loader.py:

        CodingAgent = safe_import_component("agents.coding_agent", "CodingAgent")
        ...
        class SystemTools:
            def __init__(self):
                self.coding_agent = CodingAgent() if CodingAgent else None
    """
    try:
        module = importlib.import_module(module_path)
        return getattr(module, attr_name) if attr_name else module
    except Exception as e:
        key = f"{module_path}.{attr_name}" if attr_name else module_path
        _failed_components[key] = {"error": str(e), "trace": traceback.format_exc()}
        _logger.warning(f"component '{key}' failed to import - continuing without it: {e}")
        return None


def failed_components() -> dict:
    """Everything safe_import_component() has swallowed so far this
    process, for deploy_check.py / a health endpoint to surface - a
    component silently missing should still be *visible* somewhere."""
    return dict(_failed_components)


def require(component: Optional[Any], feature_name: str) -> Any:
    """Use inside a method that truly can't degrade (rare - most Ultron
    tools already return {"error": ...} instead). Raises a clear,
    feature-named error instead of a bare AttributeError/NoneType crash
    three calls deep."""
    if component is None:
        raise RuntimeError(
            f"'{feature_name}' is unavailable in this environment - see "
            f"stability.exception_hardening.failed_components() "
            f"or dependency_validator.validate() for why."
        )
    return component
