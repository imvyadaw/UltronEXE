"""
Lazy loader / heavy-dependency isolation
=========================================
Phase 29's README flagged a real problem: `core/executor.py` imports
`windows/`, and `windows/__init__.py` does `from agents.coding_agent import
CodingAgent` and `from vision.object_detection.yolo_detector import
ObjectDetector` **at module import time**. Both of those modules import a
heavy optional third-party SDK at *their* module level too
(`from groq import Groq`, `from ultralytics import YOLO` - and `ultralytics`
itself imports `torch`). Net effect: importing `windows` - which
`core/executor.py` does unconditionally, for every tool call, whether it
needs coding/vision or not - eagerly imports Groq's client and torch.
That's slow (torch import alone is commonly 1-3s cold) and, in an
environment where `groq`/`ultralytics`/`torch` aren't installed, it used to
be a hard `ModuleNotFoundError` for the *whole* `windows` package instead of
a graceful "that one feature is unavailable".

This module gives every call site one small, consistent way to defer a
heavy/optional import to first-use instead of module-load time, in the same
"degrade, don't crash" spirit as `core/error_handler.py` and
`core/startup.py`.

Usage
-----
    from stability.lazy_loader import LazyImport

    _groq_mod = LazyImport("groq")

    class CodingAgent:
        def __init__(self):
            Groq = _groq_mod.get().Groq   # import only happens here
            ...

or, for the common "give me the attribute, not the module" case:

    from stability.lazy_loader import lazy_attr

    get_Groq = lazy_attr("groq", "Groq")
    ...
    self._client = get_Groq()(api_key=...)
"""

from __future__ import annotations

import importlib
import importlib.util
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Optional


class LazyImportError(RuntimeError):
    """Raised by LazyImport.get(strict=True) when the module is unavailable."""


@dataclass
class LazyImport:
    """Defers `import <module_name>` until `.get()` is first called.

    Thread-safe (one import attempt even if several threads race for it),
    caches both success and failure so repeated calls are cheap, and never
    raises on construction - only `.get(strict=True)` (or attribute access
    via `.available` being False and the caller choosing to raise) surfaces
    the underlying ImportError.
    """

    module_name: str
    _module: Optional[Any] = field(default=None, init=False, repr=False)
    _error: Optional[BaseException] = field(default=None, init=False, repr=False)
    _attempted: bool = field(default=False, init=False, repr=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, init=False, repr=False)
    _import_seconds: float = field(default=0.0, init=False, repr=False)

    def _ensure_attempted(self) -> None:
        if self._attempted:
            return
        with self._lock:
            if self._attempted:  # re-check inside the lock
                return
            t0 = time.monotonic()
            try:
                self._module = importlib.import_module(self.module_name)
            except BaseException as e:  # noqa: BLE001 - deliberately broad; see class docstring
                self._error = e
            finally:
                self._import_seconds = time.monotonic() - t0
                self._attempted = True

    @property
    def available(self) -> bool:
        """Cheap check that doesn't force an import: True/False/None (unknown yet)."""
        if self._attempted:
            return self._error is None
        return importlib.util.find_spec(self.module_name.split(".")[0]) is not None

    def get(self, strict: bool = True):
        """Return the imported module. Raises LazyImportError if unavailable
        and strict=True (default); returns None if strict=False."""
        self._ensure_attempted()
        if self._error is not None:
            if strict:
                raise LazyImportError(
                    f"optional dependency '{self.module_name}' is not available: {self._error}"
                ) from self._error
            return None
        return self._module

    def status(self) -> Dict[str, Any]:
        return {
            "module": self.module_name,
            "attempted": self._attempted,
            "available": (self._error is None) if self._attempted else None,
            "error": str(self._error) if self._error else None,
            "import_seconds": round(self._import_seconds, 4) if self._attempted else None,
        }


# Process-wide registry so dependency_validator.py and status endpoints can
# report on every lazy import anyone in the process has registered, without
# each caller having to thread a reference back somewhere.
_REGISTRY: Dict[str, LazyImport] = {}
_REGISTRY_LOCK = threading.Lock()


def lazy_module(module_name: str) -> LazyImport:
    """Get-or-create the shared LazyImport for `module_name`. Prefer this
    over constructing LazyImport directly so dependency_validator.py's
    report includes every heavy import registered anywhere in the process."""
    with _REGISTRY_LOCK:
        li = _REGISTRY.get(module_name)
        if li is None:
            li = LazyImport(module_name)
            _REGISTRY[module_name] = li
        return li


def lazy_attr(module_name: str, attr_name: str) -> Callable[[], Any]:
    """Return a zero-arg callable that lazily imports `module_name` and
    returns `getattr(module, attr_name)`. Convenient for the common
    "I just want the one class/function" call site."""
    li = lazy_module(module_name)

    def _get():
        return getattr(li.get(strict=True), attr_name)

    return _get


def registry_status() -> Dict[str, Dict[str, Any]]:
    """Status of every lazy import registered so far, for
    dependency_validator.py / deploy_check-style reporting."""
    with _REGISTRY_LOCK:
        items = list(_REGISTRY.items())
    return {name: li.status() for name, li in items}
