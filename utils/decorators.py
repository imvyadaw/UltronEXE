"""
utils/decorators.py - generic function decorators used across agents/,
skills/, networking/, etc. Anything that needs to log should accept an
optional logger rather than importing core.logger itself, to keep this
module dependency-free.
"""

from __future__ import annotations

import functools
import time
import warnings
from typing import Any, Callable, Optional, Tuple, Type, TypeVar

F = TypeVar("F", bound=Callable[..., Any])
T = TypeVar("T")


def retry(
    times: int = 3,
    delay_seconds: float = 1.0,
    backoff: float = 2.0,
    exceptions: Tuple[Type[BaseException], ...] = (Exception,),
) -> Callable[[F], F]:
    """Retry a function on exception, with exponential backoff.

    Used the same way networking/http_client.py and ai/cloud_models/*
    hand-roll their own retry loops today - this gives a single
    implementation any of them can adopt instead.

    >>> calls = []
    >>> @retry(times=3, delay_seconds=0)
    ... def flaky():
    ...     calls.append(1)
    ...     if len(calls) < 2:
    ...         raise ValueError("not yet")
    ...     return "ok"
    >>> flaky()
    'ok'
    """

    def decorator(func: F) -> F:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            current_delay = delay_seconds
            last_exc: Optional[BaseException] = None
            for attempt in range(1, times + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as exc:  # noqa: PERF203
                    last_exc = exc
                    if attempt == times:
                        break
                    if current_delay:
                        time.sleep(current_delay)
                    current_delay *= backoff
            raise last_exc  # type: ignore[misc]

        return wrapper  # type: ignore[return-value]

    return decorator


def timed(logger: Optional[Any] = None) -> Callable[[F], F]:
    """Log/print how long a function took. Pass a `core.logger.get_logger()`
    instance to route through the shared log file instead of stdout.

    >>> @timed()
    ... def add(a, b):
    ...     return a + b
    >>> result = add(1, 2)  # doctest: +ELLIPSIS
    add took ...ms
    >>> result
    3
    """

    def decorator(func: F) -> F:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            start = time.perf_counter()
            try:
                return func(*args, **kwargs)
            finally:
                elapsed_ms = (time.perf_counter() - start) * 1000
                message = f"{func.__qualname__} took {elapsed_ms:.1f}ms"
                if logger is not None:
                    logger.info(message)
                else:
                    print(message)

        return wrapper  # type: ignore[return-value]

    return decorator


def singleton(cls: Type[T]) -> Callable[..., T]:  # type: ignore[type-var]
    """Class decorator making `cls()` always return the same instance.
    Simpler than the module-level `_instance = None` + `get_x()`
    pattern used ad hoc in a few places (e.g. core/brain.get_brain()).

    >>> @singleton
    ... class Config:
    ...     pass
    >>> Config() is Config()
    True
    """
    instances: dict = {}

    @functools.wraps(cls)
    def get_instance(*args, **kwargs):
        if cls not in instances:
            instances[cls] = cls(*args, **kwargs)
        return instances[cls]

    return get_instance


def deprecated(reason: str = "") -> Callable[[F], F]:
    """Mark a function as deprecated; emits a DeprecationWarning on call.

    >>> import warnings
    >>> @deprecated("use new_func instead")
    ... def old_func():
    ...     return 1
    >>> with warnings.catch_warnings(record=True) as w:
    ...     warnings.simplefilter("always")
    ...     _ = old_func()
    ...     issubclass(w[-1].category, DeprecationWarning)
    True
    """

    def decorator(func: F) -> F:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            message = f"{func.__qualname__} is deprecated."
            if reason:
                message += f" {reason}"
            warnings.warn(message, DeprecationWarning, stacklevel=2)
            return func(*args, **kwargs)

        return wrapper  # type: ignore[return-value]

    return decorator
