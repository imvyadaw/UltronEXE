"""
Plugin SDK
==========
Minimal interface a plugin implements. See plugins/installed/telegram/ for
a working example (a Telegram remote-control front-end for Ultron).
"""

from abc import ABC, abstractmethod


class UltronPlugin(ABC):
    """Base class every plugin under plugins/installed/ should subclass."""

    name: str = "unnamed-plugin"

    @abstractmethod
    def register(self, brain) -> None:
        """Called once at load time. `brain` is core.brain.get_brain()."""
        raise NotImplementedError
