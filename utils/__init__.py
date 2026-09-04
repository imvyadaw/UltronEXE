"""
utils/
=======
Small, dependency-free helpers shared across the codebase (agents/,
skills/, ai/, scripts/, ...). Nothing here talks to storage/, config/,
or any external service directly - nothing in here should ever need
`from core... import` or `from ai... import`. If a helper needs that,
it belongs in the module that owns that concept, not here.

- helpers.py     - small generic functions (chunking, flattening, safe_get, ...)
- decorators.py  - @retry, @timed, @singleton, @deprecated
- validators.py  - is_valid_email / is_valid_url / is_valid_path / etc.
- constants.py   - cross-cutting literals (byte sizes, regexes, timeouts)
- formatters.py  - human_size, human_duration, truncate, slugify
- timers.py      - Timer/Stopwatch context manager + @timeout
- system.py      - OS/platform/resource info (read-only, no side effects)
"""

from utils.helpers import chunked, flatten, safe_get, deep_merge, first
from utils.decorators import retry, timed, singleton, deprecated
from utils.validators import is_valid_email, is_valid_url, is_valid_path, is_non_empty_str
from utils.constants import ONE_KB, ONE_MB, ONE_GB, DEFAULT_ENCODING, DEFAULT_TIMEOUT_SECONDS
from utils.formatters import human_size, human_duration, truncate, slugify
from utils.timers import Timer, Stopwatch
from utils.system import system_info, is_windows, is_linux, is_macos, disk_usage

__all__ = [
    "chunked",
    "flatten",
    "safe_get",
    "deep_merge",
    "first",
    "retry",
    "timed",
    "singleton",
    "deprecated",
    "is_valid_email",
    "is_valid_url",
    "is_valid_path",
    "is_non_empty_str",
    "ONE_KB",
    "ONE_MB",
    "ONE_GB",
    "DEFAULT_ENCODING",
    "DEFAULT_TIMEOUT_SECONDS",
    "human_size",
    "human_duration",
    "truncate",
    "slugify",
    "Timer",
    "Stopwatch",
    "system_info",
    "is_windows",
    "is_linux",
    "is_macos",
    "disk_usage",
]
