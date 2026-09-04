"""
Backward compat
================
Nothing in Phase 16 has moved or been renamed by this foundation phase -
every existing import (`from core.brain import get_brain`,
`from core.events import get_event_bus`, `from plugins.loader.loader
import discover_plugins`, ...) still resolves exactly where it always
did. This file exists for what comes *next*: once Phase 17.2+ starts
actually moving/renaming things, old call sites (main.py, agents/,
plugins/, ui/) must not break the same day. A rename registers a shim
here instead of leaving a dangling import somewhere in a 600+ file
codebase.

Two tools:
    @shim("old.dotted.path")   - decorator on the NEW function/class,
                                  makes the OLD dotted path still resolve
                                  to it via sys.modules, with a one-time
                                  DeprecationWarning per old path.
    check_phase16_surface()    - startup self-test asserting the handful
                                  of functions every Phase 16 caller
                                  depends on (get_brain, get_event_bus,
                                  discover_plugins, PluginManager.load_all)
                                  still exist with a callable shape, so a
                                  future accidental removal fails loudly
                                  at boot instead of silently at first use.

Nothing here is imported by Phase 16 code, and nothing here is required
for Phase 16 to keep working - it only matters once something is
deliberately deprecated via `shim()`.
"""

import sys
import types
import warnings
from typing import Callable, Dict

_warned_once: Dict[str, bool] = {}


def shim(old_dotted_path: str) -> Callable:
    """Decorator: register `old_dotted_path` (e.g.
    "core.legacy_events.get_event_bus") to resolve to the decorated
    callable. Creates any missing intermediate placeholder modules in
    sys.modules so `import core.legacy_events` and
    `from core.legacy_events import get_event_bus` both work. Emits a
    DeprecationWarning the first time the shimmed path is actually used,
    pointing at where it lives now.
    """

    def decorator(new_target: Callable) -> Callable:
        module_path, _, attr_name = old_dotted_path.rpartition(".")
        if not module_path:
            raise ValueError(f"shim() needs a dotted path, got: {old_dotted_path!r}")

        _ensure_module_chain(module_path)
        placeholder_module = sys.modules[module_path]

        def _wrapped(*args, **kwargs):
            if not _warned_once.get(old_dotted_path):
                _warned_once[old_dotted_path] = True
                warnings.warn(
                    f"'{old_dotted_path}' has moved. Update the import to use "
                    f"'{new_target.__module__}.{new_target.__qualname__}' - "
                    "this shim will keep working but may be removed in a "
                    "later phase.",
                    DeprecationWarning,
                    stacklevel=2,
                )
            return new_target(*args, **kwargs)

        _wrapped.__name__ = getattr(new_target, "__name__", attr_name)
        _wrapped.__doc__ = new_target.__doc__
        setattr(placeholder_module, attr_name, _wrapped)
        return new_target

    return decorator


def _ensure_module_chain(module_path: str) -> None:
    """Makes `import a.b.c` succeed even when a/b/c were never real
    files, by registering placeholder module objects in sys.modules for
    every segment that doesn't already exist as a real importable module."""
    parts = module_path.split(".")
    built_so_far = ""
    parent = None
    for part in parts:
        built_so_far = f"{built_so_far}.{part}" if built_so_far else part
        if built_so_far not in sys.modules:
            placeholder = types.ModuleType(built_so_far)
            placeholder.__dict__["_is_backward_compat_shim_module"] = True
            sys.modules[built_so_far] = placeholder
            if parent is not None:
                setattr(sys.modules[parent], part, placeholder)
        parent = built_so_far


# ---------------------------------------------------------------------------
# Startup self-test: fails loudly (not silently at first real use) if the
# handful of Phase 16 entry points everything else depends on ever
# disappear or change shape.
# ---------------------------------------------------------------------------
_REQUIRED_SURFACE = (
    ("core.brain", "get_brain"),
    ("core.events", "get_event_bus"),
    ("plugins.loader.loader", "discover_plugins"),
    ("plugins.manager", "PluginManager"),
    ("plugins.sdk.base", "UltronPlugin"),
)


def check_phase16_surface() -> Dict[str, bool]:
    """Imports each (module, attr) pair in _REQUIRED_SURFACE and checks
    it exists and is callable/class-like. Returns {"module.attr": bool}
    for every entry - never raises itself, so a caller (e.g.
    core/startup.py's run_startup_checks) can decide whether a missing
    entry is fatal or just a warning."""
    import importlib

    results: Dict[str, bool] = {}
    for module_path, attr_name in _REQUIRED_SURFACE:
        key = f"{module_path}.{attr_name}"
        try:
            module = importlib.import_module(module_path)
            target = getattr(module, attr_name)
            results[key] = callable(target) or isinstance(target, type)
        except Exception:
            results[key] = False
    return results
