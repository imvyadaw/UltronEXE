# ULTRON Release State

This package is a clean code release. Runtime-generated state is intentionally
not shipped. On first launch ULTRON recreates its SQLite databases, logs,
caches, screenshots and other local state as required.

Do not commit runtime databases, logs, screenshots, API credentials, or local
cache files into the release archive.
