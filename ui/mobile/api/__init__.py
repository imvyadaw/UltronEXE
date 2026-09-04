"""Mobile API package.

The Flask blueprint is imported lazily so schema-only consumers and tooling do
not require the optional web runtime merely to import ``ui.mobile.api``.
"""

__all__ = ["blueprint"]


def __getattr__(name):
    if name == "blueprint":
        from .routes import blueprint

        return blueprint
    raise AttributeError(name)
