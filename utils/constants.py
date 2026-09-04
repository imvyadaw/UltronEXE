"""
utils/constants.py - small cross-cutting literals reused in more than
one module. Anything project-specific (API URLs, model names, feature
flags) belongs in config.py / config/*.yaml instead - this file is
only for generic values that would otherwise get hardcoded in five
different places.
"""

# Byte-size multipliers, for anything doing its own size math
# (scripts/maintenance.py's human_size, upload-size checks, etc.)
ONE_KB = 1024
ONE_MB = ONE_KB * 1024
ONE_GB = ONE_MB * 1024

# Default text encoding, used anywhere a file is opened without an
# explicit encoding already decided by its caller.
DEFAULT_ENCODING = "utf-8"

# Default timeout for anything that doesn't specify its own (compare
# networking/http_client.py's own `timeout_seconds: 15` in
# config/default.yaml, which should win when both apply).
DEFAULT_TIMEOUT_SECONDS = 15

# Common date/time formats, so log lines / filenames / exports agree.
ISO_DATETIME_FORMAT = "%Y-%m-%dT%H:%M:%S"
FILENAME_TIMESTAMP_FORMAT = "%Y%m%d_%H%M%S"
