"""
ui/orb/animation.py - alias for ui/orb/orb.py.

The real implementation lives in orb.py; this file exists only so the
path `ui/orb/animation.py` from the originally requested project tree
also works, without maintaining two copies of the same code.

    from ui.orb.animation import open_orb, close_orb, is_orb_open
"""

from ui.orb.orb import open_orb, close_orb, is_orb_open

__all__ = ["open_orb", "close_orb", "is_orb_open"]
