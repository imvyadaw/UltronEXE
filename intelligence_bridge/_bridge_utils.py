"""
Bridge Utils (Phase 20.4 - Intelligence Bridge, internal)
==================================================
Shared plumbing for every *_bridge.py module in this package so the
same discovery/safe-call logic isn't duplicated 13 times over. Not
part of the public API - other packages should import the individual
bridges, not this module.

Each bridge module bridges onto a real subsystem living somewhere
under intelligence/ (or, for a couple of the older ones, core/) from
an earlier phase, but this package was written without those
subsystems' source in hand - only their names and the general
"orchestrator module exposes get_x_engine()" shape that
performance_engine.py/predictive_engine.py already established in
Phase 20.2/20.3. So every bridge here resolves its target defensively
at first-use rather than assuming an exact module path or method
name:

  resolve_module()    - tries a short list of likely dotted paths for
                         the subsystem first; if none import cleanly,
                         falls back to scanning every top-level module
                         under intelligence/ for one whose name
                         contains all of a set of keywords (e.g.
                         "world" + "state").
  resolve_singleton()  - given a resolved module, tries the
                         get_x_engine()-style singleton getters this
                         codebase already uses everywhere
                         (performance_engine.py, predictive_engine.py,
                         phase16_bridge.py's get_bridge(), etc), then
                         falls back to instantiating a plausibly-named
                         class with no arguments.
  safe_call()          - calls a method on a resolved instance if it
                         exists and is callable; any missing
                         method/attribute or raised exception is
                         swallowed and a default returned instead.
  first_success()      - tries several possible method names in turn,
                         returning the first non-None result. Lets a
                         bridge ask for "whatever this subsystem calls
                         its main query method" without knowing the
                         exact name in advance.

This makes every bridge in this package degrade to a harmless no-op
(is_available() == False, every call returns the given default)
instead of raising ImportError/AttributeError if the phase that owns
its underlying subsystem hasn't been wired in yet, was renamed, or
isn't present in a given checkout - same posture as SEARCH/
(Phase 18.5) collapsing a missing key/package to an empty result
instead of raising.

Purely additive - imported only by this package's own bridge modules.
"""

import importlib
import logging
import pkgutil
from typing import Any, Iterable, Sequence

try:
    from core.logger import get_logger

    logger = get_logger("ultron.intelligence_bridge")
except Exception:
    logger = logging.getLogger("ultron.intelligence_bridge")
    if not logger.handlers:
        logging.basicConfig(level=logging.INFO)

# Singleton-getter names already established elsewhere in this codebase
# (performance_engine.py/predictive_engine.py's get_x_engine(),
# phase16_bridge.py's get_bridge(), the SEARCH/AGENTS packages'
# get_x()) - tried on every module after any domain-specific names a
# bridge supplies of its own.
_COMMON_GETTER_NAMES = (
    "get_engine",
    "get_instance",
    "get_manager",
    "get_bridge",
)


def _iter_intelligence_submodules() -> list:
    """Best-effort listing of every top-level module/package under
    `intelligence`, used only as a last-resort fuzzy-match source.
    Returns an empty list rather than raising if `intelligence` isn't
    importable at all (e.g. this package used outside the ULTRON repo)."""
    try:
        import intelligence
    except Exception:
        return []
    try:
        return [m.name for m in pkgutil.iter_modules(intelligence.__path__, prefix="intelligence.")]
    except Exception:
        return []


def resolve_module(candidates: Sequence[str], keywords: Sequence[str] = ()):
    """Try each dotted module path in `candidates` in order; return the
    first that imports cleanly. If none do and `keywords` was given,
    fall back to scanning intelligence/'s top-level submodules for one
    whose name contains every keyword. Returns the imported module, or
    None if nothing matched. Never raises."""
    for name in candidates:
        try:
            return importlib.import_module(name)
        except ImportError:
            continue
        except Exception:
            logger.exception("intelligence_bridge: unexpected error importing %s", name)
            continue

    if keywords:
        lowered = [kw.lower() for kw in keywords]
        for modname in _iter_intelligence_submodules():
            leaf = modname.rsplit(".", 1)[-1].lower()
            if all(kw in leaf for kw in lowered):
                try:
                    return importlib.import_module(modname)
                except Exception:
                    continue
    return None


def resolve_singleton(module, getter_names: Sequence[str] = (), class_names: Sequence[str] = ()):
    """Given a resolved module (or None), try `getter_names` then the
    common get_x() names this codebase already uses, then try
    instantiating one of `class_names` with no arguments. Returns an
    instance, or None if nothing worked. Never raises."""
    if module is None:
        return None

    for getter_name in (*getter_names, *_COMMON_GETTER_NAMES):
        getter = getattr(module, getter_name, None)
        if callable(getter):
            try:
                instance = getter()
                if instance is not None:
                    return instance
            except Exception:
                logger.exception(
                    "intelligence_bridge: error calling %s.%s",
                    getattr(module, "__name__", "?"),
                    getter_name,
                )

    for class_name in class_names:
        cls = getattr(module, class_name, None)
        if isinstance(cls, type):
            try:
                return cls()
            except Exception:
                logger.exception(
                    "intelligence_bridge: error instantiating %s.%s",
                    getattr(module, "__name__", "?"),
                    class_name,
                )

    return None


def safe_call(instance: Any, method_name: str, *args, default=None, **kwargs):
    """Call instance.method_name(*args, **kwargs) if it exists and is
    callable. Missing instance/method and any raised exception both
    collapse to `default` instead of propagating."""
    if instance is None:
        return default
    fn = getattr(instance, method_name, None)
    if not callable(fn):
        return default
    try:
        result = fn(*args, **kwargs)
        return default if result is None else result
    except Exception:
        logger.exception(
            "intelligence_bridge: error calling %s on %r",
            method_name,
            instance,
        )
        return default


def first_success(instance: Any, method_names: Iterable[str], *args, default=None, **kwargs):
    """Try each name in `method_names` in order via safe_call(), return
    the first non-None result, or `default` if every one is missing/
    failed/returned None."""
    for name in method_names:
        result = safe_call(instance, name, *args, default=None, **kwargs)
        if result is not None:
            return result
    return default
