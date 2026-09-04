"""
utils/helpers.py - small generic functions with no project-specific
knowledge. If it needs config/, storage/, or a logger, it doesn't
belong here.
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, Iterator, List, Sequence, TypeVar

T = TypeVar("T")


def chunked(seq: Sequence[T], size: int) -> Iterator[List[T]]:
    """Yield successive `size`-length chunks from `seq`.

    >>> list(chunked([1, 2, 3, 4, 5], 2))
    [[1, 2], [3, 4], [5]]
    """
    if size <= 0:
        raise ValueError("size must be positive")
    for i in range(0, len(seq), size):
        yield list(seq[i : i + size])


def flatten(nested: Iterable[Any]) -> List[Any]:
    """Recursively flatten an arbitrarily nested list/tuple.

    >>> flatten([1, [2, [3, 4], 5], 6])
    [1, 2, 3, 4, 5, 6]
    """
    result: List[Any] = []
    for item in nested:
        if isinstance(item, (list, tuple)):
            result.extend(flatten(item))
        else:
            result.append(item)
    return result


def safe_get(d: Dict, *keys: str, default: Any = None) -> Any:
    """Walk nested dicts without raising on a missing key at any level.

    >>> safe_get({"a": {"b": {"c": 1}}}, "a", "b", "c")
    1
    >>> safe_get({"a": {}}, "a", "b", "c", default="missing")
    'missing'
    """
    current = d
    for key in keys:
        if not isinstance(current, dict) or key not in current:
            return default
        current = current[key]
    return current


def deep_merge(base: Dict, override: Dict) -> Dict:
    """Recursively merge `override` into a *copy* of `base`; `override`
    wins on conflicts. Neither input is mutated. Used to layer
    config/development.yaml or config/production.yaml over
    config/default.yaml without hand-writing merge logic per caller.

    >>> deep_merge({"a": 1, "b": {"x": 1}}, {"b": {"y": 2}})
    {'a': 1, 'b': {'x': 1, 'y': 2}}
    """
    merged = dict(base)
    for key, value in override.items():
        if key in merged and isinstance(merged[key], dict) and isinstance(value, dict):
            merged[key] = deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def first(iterable: Iterable[T], default: Any = None) -> Any:
    """Return the first item of an iterable, or `default` if empty."""
    for item in iterable:
        return item
    return default
